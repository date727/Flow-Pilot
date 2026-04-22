"""
统一日志配置模块
支持结构化日志输出，区分开发/生产环境格式
"""
import logging
import sys
from typing import Optional
from app.core.config import settings


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """配置并返回根日志记录器"""
    log_level = getattr(logging, (level or ("DEBUG" if settings.DEBUG else "INFO")).upper(), logging.INFO)

    # 根日志格式
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 避免重复添加 handler
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers.clear()
        root_logger.addHandler(handler)

    # 降低第三方库的日志噪音
    for noisy in ("httpx", "httpcore", "uvicorn.access", "litellm"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取命名日志记录器"""
    return logging.getLogger(name)
