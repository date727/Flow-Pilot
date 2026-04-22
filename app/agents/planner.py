"""
Planner Agent
负责将用户需求拆解为结构化的执行计划
"""
from typing import Any, Dict, List, Optional
from app.core.llm import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Prompt 模板 ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一位资深的任务规划专家（Planner Agent）。

你的职责：
1. 深入理解用户的需求和意图
2. 将复杂任务拆解为清晰、可执行的步骤
3. 识别任务中可能需要的外部工具或信息
4. 输出结构化的执行计划

输出格式要求：
- 使用编号列表（1. 2. 3. ...）
- 每步描述简洁明确，不超过 50 字
- 如需调用工具，在步骤中注明"[工具: 工具名]"
- 最后一步必须是"汇总结果并给出最终答案"

注意：
- 不要执行任务，只负责规划
- 计划步骤控制在 3-7 步之间
- 如果任务简单，可以只有 1-2 步"""

_USER_PROMPT_TEMPLATE = """请为以下任务制定执行计划：

任务描述：{task}

{context_section}请给出简洁的分步执行计划："""


class PlannerAgent:
    """
    规划 Agent

    接收用户任务描述，输出结构化的执行计划。
    支持注入历史上下文（来自 Redis 或 Milvus）以提升规划质量。
    """

    def __init__(self, llm=None):
        self._llm = llm or llm_service

    async def plan(
        self,
        task: str,
        context: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
    ) -> str:
        """
        生成任务执行计划。

        Args:
            task:        用户任务描述
            context:     可选的历史上下文（来自记忆层）
            temperature: 采样温度，规划任务建议使用较低值

        Returns:
            结构化的执行计划字符串
        """
        context_section = ""
        if context:
            context_lines = "\n".join(
                f"- {c.get('content', '')}" for c in context[:3]
            )
            context_section = f"相关历史经验：\n{context_lines}\n\n"

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            task=task,
            context_section=context_section,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.debug("[Planner] 开始规划任务: %s", task[:80])
        response = await self._llm.chat(messages, temperature=temperature)
        plan = response.choices[0].message.content.strip()
        logger.info("[Planner] 规划完成，共 %d 字符", len(plan))
        return plan

    async def replan(
        self,
        original_plan: str,
        task: str,
        failure_reason: str,
        attempt: int = 1,
    ) -> str:
        """
        基于失败原因重新规划（Reflexion 机制）。

        Args:
            original_plan:  原始计划
            task:           原始任务
            failure_reason: 失败/批评原因
            attempt:        当前重试轮次

        Returns:
            修订后的执行计划
        """
        replan_prompt = f"""原始任务：{task}

原始计划：
{original_plan}

执行反馈（第 {attempt} 次反思）：
{failure_reason}

请根据上述反馈，修订执行计划。重点解决反馈中指出的问题，保留有效的步骤。
输出修订后的完整计划："""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": replan_prompt},
        ]

        logger.info("[Planner] 第 %d 次重新规划", attempt)
        response = await self._llm.chat(messages, temperature=0.4)
        new_plan = response.choices[0].message.content.strip()
        logger.info("[Planner] 重新规划完成")
        return new_plan


# 全局单例
planner_agent = PlannerAgent()
