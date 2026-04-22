"""
LangGraph 状态机定义
实现完整的 Reflexion 闭环：Planner → Executor → Tools → Critic → (Replan | END)
"""
import asyncio
from typing import Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.engine.state import AgentState
from app.engine.nodes import (
    planner_node,
    executor_node,
    tools_node,
    critic_node,
    should_continue,
    should_replan,
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 全局连接池（单例）
_pool: Optional[AsyncConnectionPool] = None


async def get_pool() -> AsyncConnectionPool:
    """获取或创建 PostgreSQL 连接池"""
    global _pool
    db_url = settings.DATABASE_URL.replace("+asyncpg", "")

    if _pool is None or _pool.closed:
        logger.info("[Graph] 正在建立数据库连接池")
        _pool = AsyncConnectionPool(
            conninfo=db_url,
            max_size=10,
            min_size=1,
            open=False,
            kwargs={"autocommit": True},
        )
        await _pool.open()
        await _pool.wait()
        logger.info("[Graph] 数据库连接池就绪")

    return _pool


async def get_graph_app():
    """
    构建并返回编译好的 LangGraph 应用。

    图结构（Reflexion 闭环）：
    ┌─────────────────────────────────────────────────────┐
    │                                                     │
    │  START → planner → executor ──(tool_calls?)──→ tools │
    │              ↑         │                       │    │
    │              │         └──(no tools)──→ critic  │    │
    │              │                    │        │    │    │
    │              └──(needs_replan)────┘        │    │    │
    │                                            ↓    ↓    │
    │                                           END  executor│
    └─────────────────────────────────────────────────────┘
    """
    pool = await get_pool()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    # ── 构建图 ────────────────────────────────────────────────────────────────
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("critic", critic_node)

    # 入口点
    workflow.set_entry_point("planner")

    # 固定边
    workflow.add_edge("planner", "executor")
    workflow.add_edge("tools", "executor")

    # 条件边 1: Executor → Tools | Critic
    workflow.add_conditional_edges(
        "executor",
        should_continue,
        {
            "continue": "tools",   # 有工具调用 → 执行工具
            "end": "critic",       # 无工具调用 → 进入反思
        },
    )

    # 条件边 2: Critic → Planner | END
    workflow.add_conditional_edges(
        "critic",
        should_replan,
        {
            "replan": "planner",   # 质量不达标 → 重新规划
            "end": END,            # 质量达标 → 结束
        },
    )

    app = workflow.compile(checkpointer=checkpointer)
    logger.info("[Graph] LangGraph 应用编译完成（含 Reflexion 闭环）")
    return app


async def close_pool() -> None:
    """关闭数据库连接池"""
    global _pool
    if _pool and not _pool.closed:
        try:
            await _pool.close()
            logger.info("[Graph] 数据库连接池已关闭")
        except asyncio.CancelledError:
            pass
        finally:
            _pool = None
