"""loguru 日志配置 — 控制台 + 文件轮转，保留30天"""
import logging
from pathlib import Path

from loguru import logger as _loguru_logger

# 日志目录
LOG_DIR = Path.home() / ".ebay-project" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 移除默认的 stderr 配置，重新配置
_loguru_logger.remove()

# 控制台输出（INFO 及以上）
_loguru_logger.add(
    logging.StreamHandler(),
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True,
)

# 文件轮转（每天一个文件，保留30天）
_loguru_logger.add(
    LOG_DIR / "ebay-ms_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
    compression="gz",
)

# 各模块使用的 logger
def get_logger(name: str) -> "_loguru_logger":
    """按模块名返回独立的 logger 实例"""
    return _loguru_logger.bind(name=name)


# 模块级简写
logger = _loguru_logger
