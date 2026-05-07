"""
LangGraph 节点定义
包含 Planner、Executor、Tools、Critic 四个核心节点
"""
import json
import asyncio
from typing import Any, Dict, List, Literal

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.engine.state import AgentState
from app.core.llm import llm_service
from app.core.config import settings
from app.core.logging import get_logger
from app.mcp.client import MCPManager
from app.memory.milvus_memory import milvus_memory
from app.memory.context_manager import context_manager
from app.agents.planner import planner_agent
from app.agents.executor import executor_agent
from app.agents.critic import critic_agent

logger = get_logger(__name__)

# 全局 MCP 管理器（在 main.py 生命周期中初始化）
mcp_manager = MCPManager()

# Milvus 记忆检索用于规划的条数
_MEMORY_TOP_K = 3
# 工具输出最大保留字符数（防止 git diff 等大输出撑爆上下文导致超时）
_MAX_TOOL_OUTPUT_CHARS = 3000
# Executor 发送给 LLM 的最大历史消息数
_MAX_CONTEXT_MESSAGES = 30


# ── 工具调用格式转换 ──────────────────────────────────────────────────────────

def _normalize_tool_calls_for_openai(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 LangChain 风格工具调用转换为 OpenAI 兼容格式"""
    normalized = []
    for tc in tool_calls:
        if isinstance(tc, dict) and tc.get("function"):
            function_block = tc.get("function", {})
            arguments = function_block.get("arguments", "{}")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            normalized.append({
                "type": "function",
                "id": tc.get("id"),
                "function": {
                    "name": function_block.get("name", ""),
                    "arguments": arguments,
                },
            })
            continue

        args = tc.get("args", {}) if isinstance(tc, dict) else {}
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        normalized.append({
            "type": "function",
            "id": tc.get("id") if isinstance(tc, dict) else None,
            "function": {
                "name": tc.get("name", "") if isinstance(tc, dict) else "",
                "arguments": args,
            },
        })
    return normalized


def _messages_to_openai_format(messages) -> List[Dict[str, Any]]:
    """将 LangChain 消息列表转换为 OpenAI/LiteLLM 格式"""
    history = []
    for m in messages:
        if isinstance(m, HumanMessage):
            history.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            msg_dict: Dict[str, Any] = {"role": "assistant", "content": m.content or ""}
            if hasattr(m, "tool_calls") and m.tool_calls:
                msg_dict["tool_calls"] = _normalize_tool_calls_for_openai(m.tool_calls)
            history.append(msg_dict)
        elif isinstance(m, ToolMessage):
            history.append({
                "role": "tool",
                "name": m.name,
                "content": m.content,
                "tool_call_id": m.tool_call_id,
            })
    return history


# ── 节点 1: Planner ───────────────────────────────────────────────────────────

async def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    规划节点：将用户需求拆解为结构化执行计划。
    支持 Reflexion 重新规划（needs_replan=True 时）。
    从 Milvus 长期记忆检索相关历史经验注入规划上下文。
    """
    logger.info("[Planner] 开始规划任务")

    messages = state["messages"]
    task = state.get("input") or (messages[-1].content if messages else "")
    thread_id = state.get("thread_id", "")

    needs_replan = state.get("needs_replan", False)
    original_plan = state.get("plan", "")
    feedback = state.get("critic_feedback", "")
    attempt = state.get("reflection_round", 0)

    # ── 检索长期记忆（Milvus） ──────────────────────────────────────────────
    memory_context = await _retrieve_long_term_memory(task, thread_id)

    if needs_replan and original_plan and feedback:
        logger.info("[Planner] 触发重新规划（第 %d 轮反思）", attempt)
        plan = await planner_agent.replan(
            original_plan=original_plan,
            task=task,
            failure_reason=feedback,
            attempt=attempt,
        )
    else:
        plan = await planner_agent.plan(task=task, context=memory_context)

    if memory_context:
        logger.info("[Planner] 已注入 %d 条历史经验", len(memory_context))

    logger.info("[Planner] 规划完成")
    return {
        "plan": plan,
        "messages": [AIMessage(content=f"📋 执行计划（第 {attempt + 1} 轮）:\n{plan}")],
        "needs_replan": False,   # 重置标志
    }


# ── 节点 2: Executor ──────────────────────────────────────────────────────────

async def executor_node(state: AgentState) -> Dict[str, Any]:
    """
    执行节点：ReAct 模式，思考并决策（调用工具或给出最终答案）。

    上下文管理：
    1. maybe_compress: LLM 语义压缩（消息 > 20 条时将旧消息摘要化）
    2. _messages_to_openai_format: LangChain 对象 → OpenAI dict
    3. _trim_context: 规则裁剪兜底（单条 ≤2000 字符，总数 ≤30 条）
    """
    logger.info("[Executor] 开始执行")

    tools = await mcp_manager.get_all_tools()

    # ── 上下文压缩 + 格式转换 + 裁剪 ─────────────────────────────────────────
    messages = list(state["messages"])
    messages = await context_manager.maybe_compress(messages)
    history = _messages_to_openai_format(messages)
    history = _trim_context(history)

    plan = state.get("plan", "")

    response = await executor_agent.think_and_act(
        plan=plan,
        history=history,
        tools=tools if tools else None,
    )

    ai_msg = response.choices[0].message
    ai_msg_content = (ai_msg.content or "").strip()
    raw_tool_calls = getattr(ai_msg, "tool_calls", None)

    # 格式化工具调用
    formatted_tool_calls = []
    if raw_tool_calls:
        for tc in raw_tool_calls:
            raw_args = tc.function.arguments or "{}"
            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed_args = {"raw": raw_args}
            formatted_tool_calls.append({
                "name": tc.function.name,
                "args": parsed_args,
                "id": tc.id,
            })

    # 兜底：避免空输出
    if not formatted_tool_calls and not ai_msg_content:
        plan_text = state.get("plan", "")
        ai_msg_content = (
            f"已完成任务规划，建议按以下步骤执行：\n{plan_text}"
            if plan_text
            else "已完成分析，但模型未返回可展示内容。请重试或调整提示词。"
        )

    if formatted_tool_calls:
        logger.info("[Executor] 请求调用工具: %s", [tc["name"] for tc in formatted_tool_calls])
    else:
        logger.info("[Executor] 给出最终答案（%d 字符）", len(ai_msg_content))

    return {
        "messages": [AIMessage(content=ai_msg_content, tool_calls=formatted_tool_calls)],
        "output": ai_msg_content,
    }


# ── 节点 3: Tools ─────────────────────────────────────────────────────────────

async def tools_node(state: AgentState) -> Dict[str, Any]:
    """
    工具执行节点：并发执行所有待调用的 MCP 工具。
    """
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        logger.warning("[Tools] 未找到需要执行的工具调用")
        return {"messages": []}

    logger.info("[Tools] 并发执行 %d 个工具调用", len(last_message.tool_calls))

    async def run_one_tool(tool_call: Dict[str, Any]) -> ToolMessage:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        logger.debug("[Tools] 执行工具: %s, 参数: %s", tool_name, tool_args)
        result = await mcp_manager.call_tool_by_name(tool_name, tool_args)

        if result.success:
            if isinstance(result.data, list):
                content = "\n".join(
                    str(c.get("text", c)) if isinstance(c, dict) else str(c)
                    for c in result.data
                )
            else:
                content = str(result.data)
            # 截断过长输出，防止撑爆上下文
            if len(content) > _MAX_TOOL_OUTPUT_CHARS:
                content = content[:_MAX_TOOL_OUTPUT_CHARS] + (
                    f"\n\n…(已截断，原输出共 {len(content)} 字符)"
                )
            logger.debug("[Tools] 工具 %s 执行成功", tool_name)
        else:
            content = f"Error: {result.error}"
            logger.warning("[Tools] 工具 %s 执行失败: %s", tool_name, result.error)

        return ToolMessage(content=content, tool_call_id=tool_id, name=tool_name)

    tool_messages = await asyncio.gather(
        *[run_one_tool(tc) for tc in last_message.tool_calls]
    )
    return {"messages": list(tool_messages)}


# ── 节点 4: Critic ────────────────────────────────────────────────────────────

async def critic_node(state: AgentState) -> Dict[str, Any]:
    """
    反思节点：评估执行结果质量，决定是否触发重新规划。
    """
    reflection_round = state.get("reflection_round", 0) + 1
    logger.info("[Critic] 开始第 %d 轮反思评估", reflection_round)

    original_input = state.get("input", "")
    plan = state.get("plan", "")
    output = state.get("output", "")

    result = await critic_agent.evaluate(
        original_input=original_input,
        plan=plan,
        output=output,
    )

    logger.info(
        "[Critic] 评估完成: score=%.2f, passed=%s, summary=%s",
        result.score, result.passed, result.summary,
    )

    needs_replan = not result.passed and reflection_round < settings.MAX_REFLECTION_ROUNDS

    feedback_msg = (
        f"🔍 反思评估（第 {reflection_round} 轮）:\n"
        f"评分: {result.score:.2f} | {'✅ 通过' if result.passed else '❌ 需改进'}\n"
        f"{result.to_feedback_text()}"
    )

    return {
        "reflection_round": reflection_round,
        "critic_score": result.score,
        "critic_feedback": result.to_feedback_text(),
        "needs_replan": needs_replan,
        "messages": [AIMessage(content=feedback_msg)],
    }


# ── 记忆辅助函数 ──────────────────────────────────────────────────────────────

async def _retrieve_long_term_memory(task: str, thread_id: str) -> List[Dict[str, Any]]:
    """从 Milvus 检索与当前任务语义相似的历史经验"""
    try:
        embeddings = await llm_service.embed([task])
        if not embeddings or not embeddings[0]:
            return []
        results = await milvus_memory.search(
            query_embedding=embeddings[0],
            top_k=_MEMORY_TOP_K,
        )
        if results:
            logger.info("[Memory] Milvus 检索到 %d 条相关历史经验", len(results))
        return results
    except Exception as exc:
        logger.warning("[Memory] Milvus 检索失败（不影响主流程）: %s", exc)
        return []


def _trim_context(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """裁剪上下文，截断每条消息内容，控制总量不超过限制"""
    MAX_PER_MSG = 2000  # 单条消息最大字符数

    def trim_content(c):
        if isinstance(c, str) and len(c) > MAX_PER_MSG:
            return c[:MAX_PER_MSG] + f"\n…(已截断，原 {len(c)} 字符)"
        return c

    trimmed = []
    for m in history:
        m2 = dict(m)
        if "content" in m2:
            m2["content"] = trim_content(m2["content"])
        trimmed.append(m2)

    if len(trimmed) <= _MAX_CONTEXT_MESSAGES:
        return trimmed
    # 保留第一条（原始问题）和最后 20 条
    kept = trimmed[:1] + trimmed[-20:]
    logger.info("[Executor] 上下文裁剪: %d → %d 条", len(trimmed), len(kept))
    return kept


async def store_long_term_memory(
    thread_id: str,
    task: str,
    result_summary: str,
) -> None:
    """任务完成后，将任务摘要存入 Milvus 长期记忆"""
    content = f"任务: {task[:500]}\n结果: {result_summary[:500]}"
    try:
        embeddings = await llm_service.embed([content])
        if embeddings and embeddings[0]:
            await milvus_memory.store(
                thread_id=thread_id,
                content=content,
                embedding=embeddings[0],
                metadata={"task": task[:200], "result": result_summary[:200]},
            )
            logger.info("[Memory] Milvus 已存储任务经验")
    except Exception as exc:
        logger.warning("[Memory] Milvus 存储失败（不影响主流程）: %s", exc)


# ── 路由函数 ──────────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> Literal["continue", "end"]:
    """Executor 后的路由：有工具调用则继续，否则进入 Critic"""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "continue"
    return "end"


def should_replan(state: AgentState) -> Literal["replan", "end"]:
    """Critic 后的路由：需要重新规划则回到 Planner，否则结束"""
    if state.get("needs_replan", False):
        logger.info("[Router] Critic 触发重新规划")
        return "replan"
    logger.info("[Router] Critic 评估通过，任务完成")
    return "end"
