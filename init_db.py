"""
数据库初始化脚本
创建 flow_pilot 数据库（若不存在）
LangGraph Checkpoint 表由 AsyncPostgresSaver.setup() 自动创建
"""
import asyncio
import sys
import psycopg
from app.core.config import settings
from app.core.logging import setup_logging, get_logger

# Windows 专用修复
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

setup_logging()
logger = get_logger(__name__)


async def create_database():
    """创建目标数据库（若不存在）"""
    # 移除 asyncpg 前缀
    db_url = settings.DATABASE_URL.replace("+asyncpg", "")

    try:
        base_url = db_url.rsplit("/", 1)[0] + "/postgres"
        target_db = db_url.rsplit("/", 1)[-1]
        # 去掉查询参数（如 ?sslmode=...）
        target_db = target_db.split("?")[0]
    except Exception:
        logger.error("数据库连接串格式不正确，请检查 .env 中的 DATABASE_URL")
        return False

    logger.info("正在连接 PostgreSQL: %s", base_url)

    try:
        conn = await psycopg.AsyncConnection.connect(base_url, autocommit=True)
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (target_db,)
            )
            exists = await cur.fetchone()

            if not exists:
                logger.info("正在创建数据库: %s", target_db)
                await cur.execute(f'CREATE DATABASE "{target_db}"')
                logger.info("✅ 数据库 '%s' 创建成功", target_db)
            else:
                logger.info("ℹ️  数据库 '%s' 已存在，无需创建", target_db)

        await conn.close()
        return True

    except Exception as exc:
        logger.error("❌ 数据库初始化失败: %s", exc)
        logger.error("提示: 请确保 .env 中的用户名和密码正确，且 PostgreSQL 服务已启动")
        return False


async def verify_connection():
    """验证数据库连接并初始化 LangGraph Checkpoint 表"""
    from app.engine.graph import get_graph_app, close_pool

    logger.info("正在验证数据库连接并初始化 LangGraph Checkpoint 表...")
    try:
        # get_graph_app 内部会调用 checkpointer.setup() 创建所需表
        await get_graph_app()
        logger.info("✅ LangGraph Checkpoint 表初始化完成")
        await close_pool()
        return True
    except Exception as exc:
        logger.error("❌ 数据库连接验证失败: %s", exc)
        return False


async def main():
    logger.info("=" * 50)
    logger.info("Flow-Pilot 数据库初始化")
    logger.info("=" * 50)

    # 步骤 1: 创建数据库
    ok = await create_database()
    if not ok:
        sys.exit(1)

    # 步骤 2: 验证连接并初始化表结构
    ok = await verify_connection()
    if not ok:
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("✅ 数据库初始化全部完成！")
    logger.info("现在可以运行: uvicorn app.main:app --reload")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
