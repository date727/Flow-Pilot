"""
工具管理 API
提供工具列表查询、工具详情、直接调用等接口
"""
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.engine.nodes import mcp_manager
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/tools", tags=["Tools"])


# ── Request / Response 模型 ───────────────────────────────────────────────────

class ToolCallRequest(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具调用参数")


class ToolCallResponse(BaseModel):
    tool_name: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.get("/", summary="获取所有可用工具列表")
async def list_available_tools():
    """
    获取所有已连接 MCP 服务器的可用工具列表。

    返回符合 OpenAI function-calling 规范的工具定义。
    """
    try:
        tools = await mcp_manager.get_all_tools()
        return {
            "count": len(tools),
            "tools": tools,
        }
    except Exception as exc:
        logger.error("[API/tools] 获取工具列表失败: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{tool_name}", summary="获取工具详情")
async def get_tool_detail(tool_name: str):
    """
    获取指定工具的详细信息（描述、参数 Schema 等）。
    """
    try:
        tools = await mcp_manager.get_all_tools()
        for tool in tools:
            fn = tool.get("function", {})
            if fn.get("name") == tool_name:
                return {
                    "name": fn.get("name"),
                    "description": fn.get("description"),
                    "parameters": fn.get("parameters"),
                    "type": tool.get("type"),
                }
        raise HTTPException(status_code=404, detail=f"未找到工具: {tool_name}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[API/tools] 获取工具详情失败 tool=%s: %s", tool_name, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{tool_name}/call", response_model=ToolCallResponse, summary="直接调用工具")
async def call_tool(tool_name: str, request: ToolCallRequest):
    """
    直接调用指定的 MCP 工具（绕过 Agent 编排，用于调试和测试）。
    """
    logger.info("[API/tools] 直接调用工具: %s, 参数: %s", tool_name, request.arguments)
    try:
        result = await mcp_manager.call_tool_by_name(tool_name, request.arguments)
        return ToolCallResponse(
            tool_name=tool_name,
            success=result.success,
            data=result.data,
            error=result.error,
        )
    except Exception as exc:
        logger.error("[API/tools] 工具调用失败 tool=%s: %s", tool_name, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/servers/status", summary="获取 MCP 服务器连接状态")
async def get_servers_status():
    """
    获取所有 MCP 服务器的连接状态。
    """
    status = {}
    for name, client in mcp_manager.clients.items():
        status[name] = {
            "connected": client.session is not None,
            "type": client.config.get("type", "unknown"),
        }
    return {
        "total": len(mcp_manager.clients),
        "servers": status,
    }
