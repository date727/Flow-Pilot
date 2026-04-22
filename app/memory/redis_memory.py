"""
Redis 短期记忆模块
负责会话级别的上下文缓存与管理
"""
import json
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 延迟导入，避免未安装 redis 时启动失败
try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    logger.warning("redis 包未安装，RedisMemory 将以降级模式（内存字典）运行")


class RedisMemory:
    """
    Redis 短期记忆封装。

    若 Redis 不可用（未安装或连接失败），自动降级为进程内字典，
    保证系统在无 Redis 环境下仍可正常运行。
    """

    def __init__(self, url: Optional[str] = None, ttl: Optional[int] = None):
        self._url = url or settings.REDIS_URL
        self._ttl = ttl or settings.REDIS_SESSION_TTL
        self._client: Optional[Any] = None
        self._fallback: Dict[str, str] = {}   # 降级存储
        self._use_fallback = not _REDIS_AVAILABLE

    # ── 连接管理 ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if self._use_fallback:
            logger.info("[Redis] 使用内存降级模式")
            return
        try:
            self._client = aioredis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await self._client.ping()
            logger.info("[Redis] 连接成功: %s", self._url)
        except Exception as exc:
            logger.warning("[Redis] 连接失败，降级为内存模式: %s", exc)
            self._client = None
            self._use_fallback = True

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("[Redis] 已断开连接")

    # ── 会话上下文操作 ────────────────────────────────────────────────────────

    async def get_session(self, thread_id: str) -> List[Dict[str, Any]]:
        """获取会话消息历史（JSON 列表）"""
        key = self._session_key(thread_id)
        raw = await self._get(key)
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[Redis] 会话数据解析失败: %s", thread_id)
            return []

    async def save_session(self, thread_id: str, messages: List[Dict[str, Any]]) -> None:
        """保存会话消息历史"""
        key = self._session_key(thread_id)
        await self._set(key, json.dumps(messages, ensure_ascii=False), ttl=self._ttl)

    async def append_message(self, thread_id: str, message: Dict[str, Any]) -> None:
        """向会话追加一条消息"""
        messages = await self.get_session(thread_id)
        messages.append(message)
        await self.save_session(thread_id, messages)

    async def delete_session(self, thread_id: str) -> None:
        """删除会话"""
        key = self._session_key(thread_id)
        await self._delete(key)

    # ── 通用 KV 操作 ──────────────────────────────────────────────────────────

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """存储任意 JSON 可序列化值"""
        raw = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        await self._set(key, raw, ttl=ttl or self._ttl)

    async def get(self, key: str) -> Optional[Any]:
        """读取值并反序列化"""
        raw = await self._get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def delete(self, key: str) -> None:
        await self._delete(key)

    async def exists(self, key: str) -> bool:
        if self._use_fallback:
            return key in self._fallback
        try:
            return bool(await self._client.exists(key))
        except Exception as exc:
            logger.error("[Redis] exists 失败: %s", exc)
            return False

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _session_key(thread_id: str) -> str:
        return f"flow_pilot:session:{thread_id}"

    async def _get(self, key: str) -> Optional[str]:
        if self._use_fallback:
            return self._fallback.get(key)
        try:
            return await self._client.get(key)
        except Exception as exc:
            logger.error("[Redis] GET 失败 key=%s: %s", key, exc)
            return None

    async def _set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        if self._use_fallback:
            self._fallback[key] = value
            return
        try:
            await self._client.set(key, value, ex=ttl)
        except Exception as exc:
            logger.error("[Redis] SET 失败 key=%s: %s", key, exc)
            # 降级写入内存
            self._fallback[key] = value

    async def _delete(self, key: str) -> None:
        if self._use_fallback:
            self._fallback.pop(key, None)
            return
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.error("[Redis] DELETE 失败 key=%s: %s", key, exc)


# 全局单例
redis_memory = RedisMemory()
