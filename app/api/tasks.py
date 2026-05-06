"""
任务管理 API
提供任务提交、状态查询、历史记录、流式输出等接口
"""
import uuid
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.engine.graph import get_graph_app
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ── Request / Response 模型 ───────────────────────────────────────────────────

class TaskRequest(BaseModel):
    input: str = Field(..., description="任务描述或用户问题", min_length=1)
    thread_id: Optional[str] = Field(None, description="会话线程 ID，不传则自动生成")
    config: Optional[Dict[str, Any]] = Field(None, description="额外配置（可选）")
    stream: bool = Field(False, description="是否启用流式输出")


class MessageOut(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class TaskResponse(BaseModel):
    thread_id: str
    output: Optional[str]
    plan: Optional[str]
    reflection_round: int = 0
    critic_score: float = 0.0
    message_count: int = 0


class TaskHistoryResponse(BaseModel):
    thread_id: str
    messages: List[MessageOut]
    output: Optional[str]
    plan: Optional[str]
    reflection_round: int
    critic_score: float


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _build_config(thread_id: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建 LangGraph 运行配置"""
    config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if extra:
        config.update({k: v for k, v in extra.items() if k != "configurable"})
        if isinstance(extra.get("configurable"), dict):
            config["configurable"].update(extra["configurable"])
            config["configurable"]["thread_id"] = thread_id
    return config


def _serialize_messages(messages) -> List[MessageOut]:
    """将 LangChain 消息列表序列化为 API 响应格式"""
    result = []
    for m in messages:
        if isinstance(m, HumanMessage):
            result.append(MessageOut(role="user", content=m.content or ""))
        elif isinstance(m, AIMessage):
            tool_calls = None
            if hasattr(m, "tool_calls") and m.tool_calls:
                tool_calls = [
                    {
                        "name": tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", ""),
                        "args": tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}),
                        "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", ""),
                    }
                    for tc in m.tool_calls
                ]
            result.append(MessageOut(
                role="assistant",
                content=m.content or "",
                tool_calls=tool_calls,
            ))
        elif isinstance(m, ToolMessage):
            result.append(MessageOut(
                role="tool",
                content=m.content or "",
                tool_call_id=getattr(m, "tool_call_id", None),
                name=getattr(m, "name", None),
            ))
    return result


async def _persist_long_term_memory(
    thread_id: str,
    task: str,
    final_state: Dict[str, Any],
) -> None:
    """任务完成后异步存入 Milvus 长期记忆（失败不影响主流程）"""
    try:
        from app.engine.nodes import store_long_term_memory as persist

        output = final_state.get("output", "")
        plan = final_state.get("plan", "")
        score = final_state.get("critic_score", 0)
        summary = f"[评分: {score:.1f}] 计划: {plan[:200]} | 结果: {output[:300]}"
        await persist(thread_id, task, summary)
    except Exception as exc:
        logger.warning("[API] 长期记忆存储失败: %s", exc)


async def _stream_task(
    app,
    initial_input: Dict[str, Any],
    config: Dict[str, Any],
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """生成 SSE 格式的流式输出"""
    try:
        async for event in app.astream_events(initial_input, config=config, version="v2"):
            event_type = event.get("event", "")
            data = event.get("data", {})

            # 节点开始事件
            if event_type == "on_chain_start":
                node_name = event.get("name", "")
                if node_name in ("planner", "executor", "tools", "critic"):
                    yield f"data: {json.dumps({'type': 'node_start', 'node': node_name}, ensure_ascii=False)}\n\n"

            # LLM 流式 token
            elif event_type == "on_chat_model_stream":
                chunk = data.get("chunk", {})
                content = getattr(chunk, "content", "") or ""
                if content:
                    yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"

            # 节点完成事件
            elif event_type == "on_chain_end":
                node_name = event.get("name", "")
                if node_name in ("planner", "executor", "tools", "critic"):
                    node_output = data.get("output", {})
                    text = ""
                    if isinstance(node_output, dict):
                        text = (
                            node_output.get("output") or          # executor / critic 最终输出
                            node_output.get("plan") or            # planner 计划
                            node_output.get("critic_feedback") or # critic 反馈
                            ""
                        )
                    yield f"data: {json.dumps({'type': 'node_end', 'node': node_name, 'output': text}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id}, ensure_ascii=False)}\n\n"

    except Exception as exc:
        logger.error("[API/stream] 流式任务失败: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.post("/", response_model=TaskResponse, summary="提交任务")
async def create_task(request: TaskRequest):
    """
    提交一个新任务并运行 Agent 编排逻辑。

    - 自动生成 thread_id（若未提供）
    - 支持多轮对话（传入相同 thread_id）
    - 支持流式输出（stream=true 时返回 SSE 流）
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    config = _build_config(thread_id, request.config)

    initial_input = {
        "input": request.input,
        "thread_id": thread_id,
        "messages": [HumanMessage(content=request.input)],
        "metadata": {"source": "api"},
        "reflection_round": 0,
        "critic_score": 0.0,
        "critic_feedback": "",
        "needs_replan": False,
    }

    try:
        app = await get_graph_app()

        if request.stream:
            return StreamingResponse(
                _stream_task(app, initial_input, config, thread_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "X-Thread-Id": thread_id,
                },
            )

        logger.info("[API] 开始执行任务 thread_id=%s", thread_id)
        final_state = await app.ainvoke(initial_input, config=config)
        logger.info("[API] 任务完成 thread_id=%s", thread_id)

        # ── 存入长期记忆（Milvus） ──────────────────────────────────────────
        await _persist_long_term_memory(thread_id, request.input, final_state)

        return TaskResponse(
            thread_id=thread_id,
            output=final_state.get("output"),
            plan=final_state.get("plan"),
            reflection_round=final_state.get("reflection_round", 0),
            critic_score=final_state.get("critic_score", 0.0),
            message_count=len(final_state.get("messages", [])),
        )

    except Exception as exc:
        logger.error("[API] 任务执行失败 thread_id=%s: %s", thread_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{thread_id}", response_model=TaskHistoryResponse, summary="获取任务历史")
async def get_task_history(thread_id: str):
    """
    获取指定会话的完整历史状态。

    通过 LangGraph Checkpoint 读取持久化的对话历史。
    """
    config = _build_config(thread_id)
    try:
        app = await get_graph_app()
        state = await app.aget_state(config)

        if not state or not state.values:
            raise HTTPException(status_code=404, detail=f"未找到会话: {thread_id}")

        values = state.values
        messages = _serialize_messages(values.get("messages", []))

        return TaskHistoryResponse(
            thread_id=thread_id,
            messages=messages,
            output=values.get("output"),
            plan=values.get("plan"),
            reflection_round=values.get("reflection_round", 0),
            critic_score=values.get("critic_score", 0.0),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[API] 获取历史失败 thread_id=%s: %s", thread_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/", response_model=List[str], summary="列出所有会话 ID")
async def list_threads(limit: int = Query(20, ge=1, le=100)):
    """
    列出最近的会话 ID（从 Checkpoint 存储中读取）。
    """
    try:
        app = await get_graph_app()
        threads = []
        # LangGraph alist 的 limit 约束的是 checkpoint 数而非线程数，
        # 每次任务产生多个 checkpoint，因此用更大的 limit 确保覆盖
        fetch_limit = max(limit * 8, 200)
        async for checkpoint_tuple in app.checkpointer.alist(config=None, limit=fetch_limit):
            tid = checkpoint_tuple.config.get("configurable", {}).get("thread_id")
            if tid and tid not in threads:
                threads.append(tid)
                if len(threads) >= limit:
                    break
        return threads
    except Exception as exc:
        logger.error("[API] 列出会话失败: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
