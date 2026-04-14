"""
core/ebay_api/retry.py — 指数退避重试装饰器

特性：
- 装饰器模式：@with_retry(max_retries=3, base_delay=1.0)
- 仅对网络错误和 5xx 重试，4xx 不重试
- 延迟翻倍 + 随机抖动（jitter）
- 所有重试记录日志
"""
import functools
import random
import time
from typing import Callable, TypeVar

from loguru import logger

from core.ebay_api.exceptions import EbayServerError

F = TypeVar("F")


def with_retry(
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    jitter: bool = True,
    retry_on_network: bool = True,
    retry_on_5xx: bool = True,
) -> Callable[[F], F]:
    """
    重试装饰器。

    Args:
        max_retries:      最大重试次数（不含首次调用）
        base_delay:       初始延迟秒数（后续翻倍）
        jitter:           是否添加随机抖动（避免雷群效应）
        retry_on_network: 网络错误是否重试
        retry_on_5xx:     5xx 错误是否重试

    用法::

        @with_retry(max_retries=3, base_delay=1.0)
        def fetch_data():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except EbayServerError as exc:
                    if not retry_on_5xx:
                        raise
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error("{} 已达最大重试次数（{}），放弃", func.__name__, max_retries)
                        raise
                    delay = _compute_delay(attempt, base_delay, jitter)
                    logger.warning(
                        "服务器错误 [{}]，{}秒后重试（第{}/{}次）: {}",
                        exc.status_code, delay, attempt + 1, max_retries, exc
                    )
                    time.sleep(delay)

                except (OSError, IOError) as exc:
                    # 网络错误（httpx 会在此汇聚）
                    if not retry_on_network:
                        raise
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error("{} 已达最大重试次数（{}），放弃", func.__name__, max_retries)
                        raise
                    delay = _compute_delay(attempt, base_delay, jitter)
                    logger.warning(
                        "网络错误，{}秒后重试（第{}/{}次）: {}",
                        delay, attempt + 1, max_retries, exc
                    )
                    time.sleep(delay)

            # 理论上不会走到这里，但保护一下
            if last_exception:
                raise last_exception

        return wrapper  # type: ignore
    return decorator


def _compute_delay(attempt: int, base_delay: float, jitter: bool) -> float:
    """计算退避延迟：base * 2^attempt，可选加随机抖动"""
    delay = base_delay * (2 ** attempt)
    if jitter:
        delay = delay * (0.5 + random.random())  # 0.5x ~ 1.5x
    return delay
