"""
LLM 服务封装
支持 LiteLLM 多模型切换、重试、Token 统计
"""
import asyncio
from typing import List, Dict, Any, Optional
from litellm import acompletion
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 最大重试次数与退避基数（秒）
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class LLMService:
    """LiteLLM 服务封装，支持硅基流动平台及多模型切换"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model_name = model_name or settings.SILICONFLOW_MODEL
        self.api_key = api_key or settings.SILICONFLOW_API_KEY
        self.base_url = base_url or settings.SILICONFLOW_BASE_URL

        # 累计 Token 统计
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Any:
        """
        异步对话接口，内置指数退避重试。

        Args:
            messages:    符合 OpenAI 格式的消息列表
            tools:       工具定义列表（OpenAI function-calling 格式）
            temperature: 采样温度
            max_tokens:  最大生成 Token 数
            stream:      是否启用流式响应（当前版本返回完整响应）

        Returns:
            LiteLLM ModelResponse 对象
        """
        # 硅基流动需要 openai/ 前缀
        model_path = f"openai/{self.model_name}"

        kwargs: Dict[str, Any] = {
            "model": model_path,
            "messages": messages,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": temperature,
            "timeout": 60.0,  # 单次 API 调用超时（秒）
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await acompletion(**kwargs)
                self._track_usage(response)
                return response
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM 调用失败 (第 %d/%d 次)，%.1fs 后重试: %s",
                        attempt, _MAX_RETRIES, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("LLM 调用最终失败: %s", exc)

        raise last_exc  # type: ignore[misc]

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        文本向量化接口（用于 Milvus 记忆存储）。
        使用硅基流动的 embedding 模型。
        """
        from litellm import aembedding

        embed_model = f"openai/BAAI/bge-m3"
        try:
            response = await aembedding(
                model=embed_model,
                input=texts,
                api_key=self.api_key,
                api_base=self.base_url,
            )
            return [item["embedding"] for item in response.data]
        except Exception as exc:
            logger.error("Embedding 调用失败: %s", exc)
            raise

    # ── Token 统计 ────────────────────────────────────────────────────────────

    def _track_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage:
            self._total_prompt_tokens += getattr(usage, "prompt_tokens", 0)
            self._total_completion_tokens += getattr(usage, "completion_tokens", 0)

    @property
    def token_stats(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
        }

    def reset_stats(self) -> None:
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0


# 全局默认实例
llm_service = LLMService()
