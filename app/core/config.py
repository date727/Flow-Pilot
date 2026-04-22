from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, Any, List
import json

from app.mcp.models import MCPServerConfig


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Flow-Pilot"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"

    # CORS 允许的来源，逗号分隔，"*" 表示全部放行
    CORS_ORIGINS: str = "*"

    # ── API Keys ──────────────────────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None

    # SiliconFlow
    SILICONFLOW_API_KEY: Optional[str] = None
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_MODEL: str = "deepseek-ai/DeepSeek-V3"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Redis（第三阶段：短期记忆/会话缓存）────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SESSION_TTL: int = 3600          # 会话缓存过期时间（秒）

    # ── Milvus（第三阶段：长期向量记忆）──────────────────────────────────────
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "flow_pilot_memory"
    MILVUS_DIM: int = 1536                 # 向量维度，与 embedding 模型对齐

    # ── MCP Servers ───────────────────────────────────────────────────────────
    MCP_SERVERS_JSON: str = "{}"

    # ── Reflexion（第四阶段：反思机制）────────────────────────────────────────
    MAX_REFLECTION_ROUNDS: int = 3         # 最大反思轮次
    REFLECTION_SCORE_THRESHOLD: float = 0.7  # 质量评分阈值，低于此值触发重试

    # ── LangSmith（第五阶段：可观测性）────────────────────────────────────────
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "flow-pilot"

    # ─────────────────────────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        try:
            raw = json.loads(self.MCP_SERVERS_JSON)
        except json.JSONDecodeError as e:
            print(f"--- [Config] MCP_SERVERS_JSON 不是合法 JSON: {e} ---")
            return {}

        if not isinstance(raw, dict):
            print("--- [Config] MCP_SERVERS_JSON 顶层必须是对象 ---")
            return {}

        validated: Dict[str, Dict[str, Any]] = {}
        for server_name, cfg in raw.items():
            try:
                validated[server_name] = MCPServerConfig.model_validate(cfg).model_dump(exclude_none=True)
            except Exception as e:
                print(f"--- [Config] MCP 服务器配置无效 ({server_name}): {e} ---")
        return validated

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# 全局单例
settings = Settings()
