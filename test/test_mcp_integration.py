import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.core.config import settings
from app.engine.nodes import mcp_manager

# Windows 专用修复
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main():
    """真实 MCP 集成验证（不使用 mock）。"""
    servers = settings.mcp_servers
    if not servers:
        print("❌ 未检测到可用的 MCP 服务器配置，请先在 .env 中设置 MCP_SERVERS_JSON。")
        print("示例: MCP_SERVERS_JSON={\"weather\":{\"type\":\"stdio\",\"command\":\"uvx\",\"args\":[\"mcp-server-weather\"]}}")
        raise SystemExit(1)

    print(f"--- [MCP Test] 检测到 {len(servers)} 个服务器配置: {list(servers.keys())} ---")

    try:
        await mcp_manager.initialize_from_config(servers)

        tools = await mcp_manager.get_all_tools()
        print(f"--- [MCP Test] 发现工具数量: {len(tools)} ---")

        if not tools:
            print("❌ 已连接服务器但未发现任何工具。请检查 MCP Server 是否正常暴露工具。")
            raise SystemExit(2)

        for idx, tool in enumerate(tools, start=1):
            fn = tool.get("function", {})
            print(f"  {idx}. {fn.get('name')} - {fn.get('description', '')}")

        # 可选：执行真实工具调用（按环境变量指定）
        tool_name = os.getenv("MCP_TEST_TOOL_NAME")
        tool_args_json = os.getenv("MCP_TEST_TOOL_ARGS_JSON", "{}")

        if tool_name:
            try:
                tool_args = json.loads(tool_args_json)
            except json.JSONDecodeError:
                print("❌ MCP_TEST_TOOL_ARGS_JSON 不是合法 JSON。")
                raise SystemExit(3)

            print(f"--- [MCP Test] 调用工具: {tool_name}, 参数: {tool_args} ---")
            result = await mcp_manager.call_tool_by_name(tool_name, tool_args)
            if result.success:
                print(f"✅ 工具调用成功: {result.data}")
            else:
                print(f"❌ 工具调用失败: {result.error}")
                raise SystemExit(4)
        else:
            print("--- [MCP Test] 未设置 MCP_TEST_TOOL_NAME，跳过真实调用，仅验证发现能力 ---")

        print("✅ MCP 第二阶段关键能力验证通过。")

    finally:
        await mcp_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
