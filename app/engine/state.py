"""
LangGraph Agent 状态定义
包含完整的 Reflexion 闭环所需字段
"""
from typing import TypedDict, Annotated, Sequence, Dict, Any, Optional
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Flow-Pilot Agent 状态

    字段说明：
    - input:              用户原始输入
    - messages:           对话历史（HumanMessage / AIMessage / ToolMessage）
    - plan:               当前执行计划（Planner 输出）
    - metadata:           任务元数据（来源、配置等）
    - output:             最终输出结果
    - reflection_round:   当前反思轮次（0 = 未反思）
    - critic_score:       最近一次 Critic 评分（0.0 ~ 1.0）
    - critic_feedback:    最近一次 Critic 反馈文本
    - needs_replan:       是否需要重新规划
    """

    # ── 核心字段 ──────────────────────────────────────────────────────────────
    input: str

    thread_id: str                 # 会话 ID，用于记忆存取

    # Annotated + operator.add 允许节点向列表中追加新消息
    messages: Annotated[Sequence[BaseMessage], operator.add]

    plan: str

    metadata: Dict[str, Any]

    output: Optional[str]

    # ── Reflexion 字段 ────────────────────────────────────────────────────────
    reflection_round: int          # 当前反思轮次

    critic_score: float            # Critic 评分

    critic_feedback: str           # Critic 反馈文本

    needs_replan: bool             # 是否触发重新规划
