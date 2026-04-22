from pydantic import BaseModel, Field, model_validator
from typing import Dict, Any, Optional, Literal


class MCPServerConfig(BaseModel):
    """MCP 服务配置模型。"""

    type: Literal["stdio", "sse"] = Field("stdio", description="传输类型")
    command: Optional[str] = Field(None, description="stdio 模式下的启动命令")
    args: list[str] = Field(default_factory=list, description="stdio 模式下的参数")
    env: Optional[Dict[str, str]] = Field(None, description="stdio 模式下的环境变量")
    url: Optional[str] = Field(None, description="sse 模式下的服务地址")

    @model_validator(mode="after")
    def validate_transport_fields(self):
        if self.type == "stdio" and not self.command:
            raise ValueError("stdio 模式必须提供 command")
        if self.type == "sse" and not self.url:
            raise ValueError("sse 模式必须提供 url")
        return self

class ToolDefinition(BaseModel):
    """MCP 工具定义"""
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具功能描述")
    input_schema: Dict[str, Any] = Field(..., description="参数的 JSON Schema")

class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool = Field(..., description="是否执行成功")
    data: Optional[Any] = Field(None, description="执行成功的返回数据")
    error: Optional[str] = Field(None, description="错误信息")
