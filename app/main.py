"""
Flow-Pilot FastAPI 应用入口
"""
import time
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.engine.nodes import mcp_manager
from app.engine.graph import close_pool
from app.memory.redis_memory import redis_memory
from app.memory.milvus_memory import milvus_memory
from app.api.tasks import router as tasks_router
from app.api.tools import router as tools_router

# 初始化日志（必须在其他模块之前）
setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


# ── 生命周期管理 ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理应用生命周期内的资源"""
    logger.info("=" * 60)
    logger.info("正在启动 %s ...", settings.APP_NAME)

    # 1. 连接 Redis（短期记忆）
    logger.info("正在连接 Redis ...")
    await redis_memory.connect()

    # 2. 连接 Milvus（长期记忆）
    logger.info("正在连接 Milvus ...")
    await milvus_memory.connect()

    # 3. 初始化 MCP 服务器
    logger.info("正在连接 MCP 服务器 ...")
    await mcp_manager.initialize_from_config(settings.mcp_servers)

    logger.info("%s 启动完成 ✅", settings.APP_NAME)
    logger.info("=" * 60)

    yield

    # ── 关闭阶段 ──────────────────────────────────────────────────────────────
    logger.info("正在关闭 %s ...", settings.APP_NAME)

    await mcp_manager.shutdown()
    await redis_memory.disconnect()
    await milvus_memory.disconnect()
    await close_pool()

    logger.info("%s 已安全关闭 ✅", settings.APP_NAME)


# ── FastAPI 应用 ──────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    description=(
        "Flow-Pilot: 基于 MCP 协议与 Reflexion 工作流的异构任务编排 Agent 框架\n\n"
        "## 核心特性\n"
        "- 🔧 **MCP 协议**: 标准化工具调用，支持 stdio/sse 两种传输方式\n"
        "- 🔄 **Reflexion 闭环**: Plan → Execute → Critic → Re-plan 自我纠错\n"
        "- 🧠 **分层记忆**: Redis 短期缓存 + Milvus 长期向量记忆\n"
        "- ⚡ **LangGraph**: 基于状态机的可持久化工作流\n"
        "- 🌊 **流式输出**: SSE 实时推送执行过程"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── 中间件 ────────────────────────────────────────────────────────────────────

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求耗时日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理的异常 %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误", "message": str(exc)},
    )


# ── 路由注册 ──────────────────────────────────────────────────────────────────

app.include_router(tasks_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")


# ── 基础端点 ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Root"], summary="前端界面")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health", tags=["Root"], summary="健康检查")
async def health_check():
    """
    检查各依赖服务的连接状态。
    """
    # Redis 状态
    redis_ok = not redis_memory._use_fallback
    if redis_ok:
        try:
            await redis_memory._client.ping()
        except Exception:
            redis_ok = False

    # Milvus 状态
    milvus_ok = not milvus_memory._use_fallback and milvus_memory._collection is not None

    # MCP 状态
    mcp_connected = len(mcp_manager.clients)

    return {
        "status": "healthy",
        "services": {
            "redis": "connected" if redis_ok else "fallback (in-memory)",
            "milvus": "connected" if milvus_ok else "fallback (in-memory)",
            "mcp_servers": f"{mcp_connected} server(s) connected",
        },
        "config": {
            "app_name": settings.APP_NAME,
            "debug": settings.DEBUG,
            "max_reflection_rounds": settings.MAX_REFLECTION_ROUNDS,
        },
    }


@app.get("/metrics", tags=["Root"], summary="Token 使用统计")
async def get_metrics():
    """获取 LLM Token 使用统计"""
    from app.core.llm import llm_service
    return {
        "llm_token_stats": llm_service.token_stats,
        "model": llm_service.model_name,
    }


# ── 静态文件（前端界面）────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

# ── 本地启动 ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
