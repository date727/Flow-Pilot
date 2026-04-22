from typing import Dict, Any, List, Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from app.mcp.models import ToolDefinition, ToolResult

class MCPClient:
    """MCP 协议客户端封装"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.session: Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()

    async def connect(self):
        """建立连接并初始化 Session"""
        transport_type = self.config.get("type", "stdio")
        
        if transport_type == "stdio":
            server_params = StdioServerParameters(
                command=self.config.get("command"),
                args=self.config.get("args", []),
                env=self.config.get("env")
            )
            # 进入 stdio_client 上下文
            read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
            self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        
        elif transport_type == "sse":
            url = self.config.get("url")
            # 进入 sse_client 上下文
            read, write = await self._exit_stack.enter_async_context(sse_client(url))
            self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        
        else:
            raise ValueError(f"不支持的传输类型: {transport_type}")
        
        # 初始化协议
        await self.session.initialize()
        print(f"--- MCP Client [{self.name}] 已连接 ---")

    async def list_tools(self) -> List[ToolDefinition]:
        """获取工具列表"""
        if not self.session:
            raise RuntimeError("Client 未连接")
        
        response = await self.session.list_tools()
        tools = []
        for t in response.tools:
            tools.append(ToolDefinition(
                name=t.name,
                description=t.description,
                input_schema=t.inputSchema
            ))
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """调用指定工具"""
        if not self.session:
            raise RuntimeError("Client 未连接")
        
        try:
            result = await self.session.call_tool(name, arguments)
            return ToolResult(success=True, data=result.content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def disconnect(self):
        """断开连接并清理资源"""
        await self._exit_stack.aclose()
        self.session = None
        print(f"--- MCP Client [{self.name}] 已断开 ---")

class MCPManager:
    """管理多个 MCP 客户端"""
    
    def __init__(self, allowed_tools: Optional[List[str]] = None, denied_tools: Optional[List[str]] = None):
        self.clients: Dict[str, MCPClient] = {}
        # 基础权限过滤
        self.allowed_tools = allowed_tools
        self.denied_tools = denied_tools
        # tool_name -> client_name 缓存，减少每次调用时重复 list_tools
        self._tool_owner_cache: Dict[str, str] = {}

    def _tool_allowed(self, tool_name: str) -> bool:
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return False
        if self.denied_tools and tool_name in self.denied_tools:
            return False
        return True

    async def initialize_from_config(self, config: Dict[str, Any]):
        """根据配置自动初始化多个 Client"""
        if not config:
            print("--- [MCP] 未检测到 MCP 服务器配置，跳过初始化 ---")
            return
            
        for name, server_cfg in config.items():
            try:
                await self.add_client(name, server_cfg)
            except Exception as e:
                print(f"--- [MCP] 初始化服务器 {name} 失败: {str(e)} ---")

    async def add_client(self, name: str, config: Dict[str, Any]):
        client = MCPClient(name, config)
        await client.connect()
        self.clients[name] = client
        self._tool_owner_cache.clear()

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """从所有 Client 中汇总工具，并执行权限过滤 (返回符合 OpenAI 规范的格式)"""
        all_tools = []
        self._tool_owner_cache.clear()
        for client_name, client in self.clients.items():
            try:
                tools = await client.list_tools()
                for t in tools:
                    if not self._tool_allowed(t.name):
                        continue

                    # 记录工具归属，加速后续按名称调用
                    self._tool_owner_cache.setdefault(t.name, client_name)

                    # 转换为 OpenAI 要求的工具定义格式
                    tool_dict = {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.input_schema  # MCP 的 input_schema 即对应 JSON Schema
                        }
                    }
                    all_tools.append(tool_dict)
            except Exception as e:
                print(f"--- [MCP] 从 {client_name} 获取工具列表失败: {str(e)} ---")
        return all_tools

    async def call_tool(self, client_name: str, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        if client_name not in self.clients:
            return ToolResult(success=False, error=f"未找到 Client: {client_name}")
        return await self.clients[client_name].call_tool(tool_name, arguments)

    async def call_tool_by_name(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """根据工具名称尝试在所有 Client 中寻找并执行"""
        if not self._tool_allowed(tool_name):
            return ToolResult(success=False, error=f"工具无权限调用: {tool_name}")

        owner = self._tool_owner_cache.get(tool_name)
        if owner and owner in self.clients:
            return await self.clients[owner].call_tool(tool_name, arguments)

        # 缓存未命中时刷新一次工具列表并重试
        await self.get_all_tools()
        owner = self._tool_owner_cache.get(tool_name)
        if owner and owner in self.clients:
            return await self.clients[owner].call_tool(tool_name, arguments)

        # 兜底：兼容未构建缓存的场景
        for client in self.clients.values():
            # 检查该 client 是否有此工具
            tools = await client.list_tools()
            if any(t.name == tool_name for t in tools):
                return await client.call_tool(tool_name, arguments)
        return ToolResult(success=False, error=f"在所有注册的 Client 中均未找到工具: {tool_name}")

    async def shutdown(self):
        for client in self.clients.values():
            await client.disconnect()
        self.clients.clear()
        self._tool_owner_cache.clear()
