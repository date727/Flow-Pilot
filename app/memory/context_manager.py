"""
上下文管理器
负责上下文压缩与修剪，提升长对话下的模型鲁棒性
"""
from typing import Any, Dict, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from app.core.llm import llm_service
from app.core.logging import get_logger

logger = get_logger(__name__)

# 触发压缩的消息数量阈值
_COMPRESS_THRESHOLD = 20
# 压缩后保留的最近消息数
_KEEP_RECENT = 6


class ContextManager:
    """
    上下文管理器

    功能：
    1. 消息修剪：超过阈值时删除旧消息，保留最近 N 条
    2. 上下文压缩：将旧消息摘要化，减少 Token 消耗
    3. 重要消息保留：始终保留第一条用户消息（原始任务）
    """

    def __init__(
        self,
        compress_threshold: int = _COMPRESS_THRESHOLD,
        keep_recent: int = _KEEP_RECENT,
        llm=None,
    ):
        self._threshold = compress_threshold
        self._keep_recent = keep_recent
        self._llm = llm or llm_service

    async def maybe_compress(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """
        若消息数量超过阈值，执行上下文压缩。

        压缩策略：
        - 保留第一条 HumanMessage（原始任务）
        - 将中间消息摘要化为一条 AIMessage
        - 保留最近 keep_recent 条消息

        Args:
            messages: 当前消息列表

        Returns:
            压缩后的消息列表
        """
        if len(messages) <= self._threshold:
            return messages

        logger.info(
            "[ContextManager] 消息数 %d 超过阈值 %d，开始压缩",
            len(messages), self._threshold,
        )

        # 找到第一条用户消息
        first_human = next(
            (m for m in messages if isinstance(m, HumanMessage)), None
        )

        # 需要压缩的消息（排除最近 keep_recent 条）
        recent = messages[-self._keep_recent:]
        to_compress = messages[:-self._keep_recent]

        # 如果第一条用户消息在 recent 中，直接修剪
        if first_human in recent:
            logger.info("[ContextManager] 修剪完成，保留 %d 条消息", len(recent))
            return recent

        # 生成摘要
        summary = await self._summarize(to_compress)
        summary_msg = AIMessage(content=f"[历史摘要]\n{summary}")

        result = []
        if first_human:
            result.append(first_human)
        result.append(summary_msg)
        result.extend(recent)

        logger.info(
            "[ContextManager] 压缩完成: %d → %d 条消息",
            len(messages), len(result),
        )
        return result

    def trim(
        self,
        messages: List[BaseMessage],
        max_count: Optional[int] = None,
    ) -> List[BaseMessage]:
        """
        简单修剪：直接截断旧消息，保留最近 N 条。
        不调用 LLM，适合对延迟敏感的场景。
        """
        limit = max_count or self._keep_recent
        if len(messages) <= limit:
            return messages
        trimmed = messages[-limit:]
        logger.debug("[ContextManager] 修剪: %d → %d 条消息", len(messages), len(trimmed))
        return trimmed

    async def _summarize(self, messages: List[BaseMessage]) -> str:
        """调用 LLM 生成消息摘要"""
        # 将消息转为文本
        lines = []
        for m in messages:
            if isinstance(m, HumanMessage):
                lines.append(f"用户: {m.content}")
            elif isinstance(m, AIMessage):
                content = m.content or ""
                if content:
                    lines.append(f"助手: {content[:200]}")
            elif isinstance(m, ToolMessage):
                lines.append(f"工具({m.name}): {m.content[:100]}")

        history_text = "\n".join(lines)

        prompt = f"""请将以下对话历史压缩为简洁的摘要（不超过 200 字），保留关键信息和决策：

{history_text}

摘要："""

        try:
            response = await self._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("[ContextManager] 摘要生成失败: %s", exc)
            return f"（历史对话摘要生成失败，共 {len(messages)} 条消息）"


# 全局单例
context_manager = ContextManager()
