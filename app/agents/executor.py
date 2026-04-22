"""
Executor Agent
负责按照计划执行任务，通过 ReAct 模式调用工具
"""
from typing import Any, Dict, List, Optional
from app.core.llm import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Prompt 模板 ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """你是一个高效的执行 Agent（Executor Agent）。

当前任务计划：
{plan}

你的职责：
1. 严格按照计划逐步执行任务
2. 当需要获取外部信息或执行操作时，调用合适的工具
3. 观察工具返回结果，决定下一步行动
4. 当所有步骤完成后，给出清晰、完整的最终答案

执行原则：
- 每次只做一件事（思考 → 行动 → 观察）
- 工具调用失败时，尝试替代方案或说明原因
- 最终答案必须直接回答用户的原始问题
- 如果没有可用工具，基于已有知识直接回答"""


class ExecutorAgent:
    """
    执行 Agent

    实现 ReAct（Reasoning + Acting）模式：
    思考（Thought）→ 行动（Action/Tool Call）→ 观察（Observation）→ 循环
    """

    def __init__(self, llm=None):
        self._llm = llm or llm_service

    def build_system_prompt(self, plan: str) -> str:
        """根据当前计划构建系统提示词"""
        return _SYSTEM_PROMPT_TEMPLATE.format(plan=plan or "暂无明确计划，请根据用户需求灵活执行")

    def build_messages(
        self,
        plan: str,
        history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        构建完整的消息列表（系统提示 + 历史对话）。

        Args:
            plan:    当前执行计划
            history: 已格式化的对话历史（OpenAI 格式）

        Returns:
            完整消息列表
        """
        system_msg = {"role": "system", "content": self.build_system_prompt(plan)}
        return [system_msg] + history

    async def think_and_act(
        self,
        plan: str,
        history: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> Any:
        """
        执行一轮思考与行动。

        Args:
            plan:        当前执行计划
            history:     对话历史（OpenAI 格式）
            tools:       可用工具列表
            temperature: 采样温度

        Returns:
            LiteLLM ModelResponse
        """
        messages = self.build_messages(plan, history)
        logger.debug("[Executor] 开始思考，历史消息数: %d，可用工具数: %d",
                     len(history), len(tools) if tools else 0)
        response = await self._llm.chat(messages, tools=tools, temperature=temperature)
        return response


# 全局单例
executor_agent = ExecutorAgent()
