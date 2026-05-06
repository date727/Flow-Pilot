"""
Milvus 长期向量记忆模块
负责历史经验的语义存储与检索（RAG）
"""
import json
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 延迟导入
try:
    from pymilvus import (
        connections,
        Collection,
        CollectionSchema,
        FieldSchema,
        DataType,
        utility,
    )
    _MILVUS_AVAILABLE = True
except ImportError:
    _MILVUS_AVAILABLE = False
    logger.warning("pymilvus 包未安装，MilvusMemory 将以降级模式（内存列表）运行")


class MilvusMemory:
    """
    Milvus 长期向量记忆封装。

    若 Milvus 不可用，自动降级为进程内列表（仅支持精确匹配），
    保证系统在无 Milvus 环境下仍可正常运行。
    """

    # Collection 字段定义
    _FIELDS = {
        "id": "主键",
        "thread_id": "会话 ID",
        "content": "原始文本内容（最长 4096 字符）",
        "embedding": "向量",
        "metadata_json": "附加元数据（JSON 字符串）",
        "created_at": "创建时间戳",
    }

    def __init__(self):
        self._collection: Optional[Any] = None
        self._use_fallback = not _MILVUS_AVAILABLE
        self._fallback: List[Dict[str, Any]] = []

    # ── 连接管理 ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if self._use_fallback:
            logger.info("[Milvus] 使用内存降级模式")
            return
        try:
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
            self._collection = self._get_or_create_collection()
            logger.info(
                "[Milvus] 连接成功: %s:%d, collection=%s",
                settings.MILVUS_HOST,
                settings.MILVUS_PORT,
                settings.MILVUS_COLLECTION,
            )
        except Exception as exc:
            logger.warning("[Milvus] 连接失败，降级为内存模式: %s", exc)
            self._use_fallback = True

    async def disconnect(self) -> None:
        if not self._use_fallback and _MILVUS_AVAILABLE:
            try:
                connections.disconnect("default")
                logger.info("[Milvus] 已断开连接")
            except Exception:
                pass

    # ── 记忆操作 ──────────────────────────────────────────────────────────────

    async def store(
        self,
        thread_id: str,
        content: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """存储一条记忆"""
        if self._use_fallback:
            self._fallback.append({
                "thread_id": thread_id,
                "content": content,
                "embedding": embedding,
                "metadata": metadata or {},
                "created_at": time.time(),
            })
            return

        try:
            self._collection.insert([
                [thread_id],
                [content[:4096]],
                [embedding],
                [json.dumps(metadata or {}, ensure_ascii=False)],
                [int(time.time())],
            ])
            self._collection.flush()
        except Exception as exc:
            logger.error("[Milvus] 存储失败: %s", exc)

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        thread_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        语义检索最相关的记忆。

        Args:
            query_embedding: 查询向量
            top_k:           返回条数
            thread_id:       若指定，则只在该会话内检索

        Returns:
            记忆列表，每条包含 content、score、metadata
        """
        if self._use_fallback:
            return self._fallback_search(query_embedding, top_k, thread_id)

        try:
            expr = f'thread_id == "{thread_id}"' if thread_id else None
            results = self._collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit=top_k,
                expr=expr,
                output_fields=["thread_id", "content", "metadata_json", "created_at"],
            )
            hits = []
            for hit in results[0]:
                fields = hit.fields
                hits.append({
                    "content": fields.get("content"),
                    "score": hit.score,
                    "thread_id": fields.get("thread_id"),
                    "metadata": json.loads(fields.get("metadata_json", "{}")),
                    "created_at": fields.get("created_at"),
                })
            return hits
        except Exception as exc:
            logger.error("[Milvus] 检索失败: %s", exc)
            return []

    async def delete_by_thread(self, thread_id: str) -> None:
        """删除某会话的所有记忆"""
        if self._use_fallback:
            self._fallback = [m for m in self._fallback if m["thread_id"] != thread_id]
            return
        try:
            self._collection.delete(f'thread_id == "{thread_id}"')
        except Exception as exc:
            logger.error("[Milvus] 删除失败: %s", exc)

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    def _get_or_create_collection(self) -> Any:
        col_name = settings.MILVUS_COLLECTION
        if utility.has_collection(col_name):
            col = Collection(col_name)
            # 校验 schema 维度是否匹配当前配置
            try:
                emb_field = next(f for f in col.schema.fields if f.name == "embedding")
                existing_dim = emb_field.params.get("dim")
                if existing_dim != settings.MILVUS_DIM:
                    logger.warning(
                        "[Milvus] Collection embedding 维度不匹配 (现有=%d, 配置=%d)，正在重建...",
                        existing_dim, settings.MILVUS_DIM,
                    )
                    col.release()
                    utility.drop_collection(col_name)
                else:
                    col.load()
                    return col
            except StopIteration:
                logger.warning("[Milvus] Collection 缺少 embedding 字段，正在重建...")
                col.release()
                utility.drop_collection(col_name)

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="thread_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.MILVUS_DIM),
            FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="created_at", dtype=DataType.INT64),
        ]
        schema = CollectionSchema(fields, description="Flow-Pilot 长期记忆")
        col = Collection(col_name, schema)

        # 创建 IVF_FLAT 索引
        col.create_index(
            field_name="embedding",
            index_params={"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 128}},
        )
        col.load()
        logger.info("[Milvus] Collection '%s' 已创建并加载", col_name)
        return col

    def _fallback_search(
        self,
        query_embedding: List[float],
        top_k: int,
        thread_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """降级模式：余弦相似度暴力搜索"""
        import math

        def cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb + 1e-9)

        candidates = self._fallback
        if thread_id:
            candidates = [m for m in candidates if m["thread_id"] == thread_id]

        scored = [
            {**m, "score": cosine(query_embedding, m["embedding"])}
            for m in candidates
            if m.get("embedding")
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


# 全局单例
milvus_memory = MilvusMemory()
