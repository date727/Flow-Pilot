"""
Critic Agent（反思 Agent）
负责评估执行结果的质量，触发 Reflexion 重试机制
"""
import json
from typing import Any, Dict, Optional
from app.core.llm import llm_service
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Prompt 模板 ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一位严格的质量评审专家（Critic Agent）。

你的职责：
1. 评估 Agent 的执行结果是否完整、准确地回答了用户的原始问题
2. 识别执行过程中的错误、遗漏或不合理之处
3. 给出具体的改进建议
4. 输出一个 0.0 ~ 1.0 的质量评分

评分标准：
- 1.0: 完美回答，完全满足需求
- 0.8-0.9: 良好，基本满足需求，有小瑕疵
- 0.6-0.7: 一般，部分满足需求，有明显不足
- 0.4-0.5: 较差，未能有效回答问题
- 0.0-0.3: 失败，答案错误或完全偏离

输出格式（严格 JSON）：
{
  "score": 0.85,
  "passed": true,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"],
  "summary": "总体评价（一句话）"
}"""

_USER_PROMPT_TEMPLATE = """请评估以下执行结果：

原始用户问题：
{original_input}

执行计划：
{plan}

执行结果：
{output}

请给出严格的质量评估（JSON 格式）："""


class CriticResult:
    """反思评估结果"""

    def __init__(
        self,
        score: float,
        passed: bool,
        issues: list,
        suggestions: list,
        summary: str,
    ):
        self.score = score
        self.passed = passed
        self.issues = issues
        self.suggestions = suggestions
        self.summary = summary

    def to_feedback_text(self) -> str:
        """生成给 Planner 的反馈文本"""
        lines = [f"质量评分: {self.score:.2f}", f"评价: {self.summary}"]
        if self.issues:
            lines.append("发现的问题:")
            lines.extend(f"  - {issue}" for issue in self.issues)
        if self.suggestions:
            lines.append("改进建议:")
            lines.extend(f"  - {sug}" for sug in self.suggestions)
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"CriticResult(score={self.score:.2f}, passed={self.passed}, "
            f"summary='{self.summary}')"
        )


class CriticAgent:
    """
    反思 Agent

    评估执行结果质量，决定是否需要触发 Reflexion 重试。
    评分低于阈值时，生成详细的改进建议供 Planner 重新规划。
    """

    def __init__(self, llm=None, threshold: Optional[float] = None):
        self._llm = llm or llm_service
        self._threshold = threshold or settings.REFLECTION_SCORE_THRESHOLD

    async def evaluate(
        self,
        original_input: str,
        plan: str,
        output: str,
        temperature: float = 0.2,
    ) -> CriticResult:
        """
        评估执行结果。

        Args:
            original_input: 用户原始输入
            plan:           执行计划
            output:         执行结果
            temperature:    采样温度（评估任务建议低温）

        Returns:
            CriticResult 评估结果
        """
        # 截断过长的输入，评审不需要看几万字也能判断质量
        plan_trimmed = plan[:1500] if len(plan) > 1500 else plan
        output_trimmed = output[:3000] if len(output) > 3000 else output

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            original_input=original_input[:1000],
            plan=plan_trimmed or "（无明确计划）",
            output=output_trimmed or "（无输出）",
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.debug("[Critic] 开始评估执行结果")
        response = await self._llm.chat(messages, temperature=temperature)
        raw = response.choices[0].message.content.strip()

        return self._parse_result(raw)

    def _parse_result(self, raw: str) -> CriticResult:
        """解析 LLM 返回的 JSON 评估结果"""
        # 尝试提取 JSON 块
        try:
            # 处理 markdown 代码块包裹的情况
            if "```" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                raw = raw[start:end]

            data: Dict[str, Any] = json.loads(raw)
            score = float(data.get("score", 0.5))
            passed = data.get("passed", score >= self._threshold)
            if not isinstance(passed, bool):
                passed = score >= self._threshold

            return CriticResult(
                score=score,
                passed=passed,
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                summary=data.get("summary", ""),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("[Critic] 解析评估结果失败: %s，原始内容: %s", exc, raw[:200])
            # 降级：根据关键词判断
            score = 0.5
            passed = score >= self._threshold
            return CriticResult(
                score=score,
                passed=passed,
                issues=["无法解析评估结果"],
                suggestions=["请检查 LLM 输出格式"],
                summary="评估结果解析失败，使用默认评分",
            )

    @property
    def threshold(self) -> float:
        return self._threshold


# 全局单例
critic_agent = CriticAgent()
