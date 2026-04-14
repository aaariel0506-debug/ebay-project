"""
core/ebay_api/cache.py — eBay API 响应缓存

特性：
- 对 GET 请求做短期缓存（TTL 可配置，默认 5 分钟）
- 相同 URL + query params 在 TTL 内直接返回缓存
- POST/PUT/DELETE 不缓存
- 提供手动清除方法
"""
import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

DEFAULT_TTL_SECONDS = 300  # 5 分钟


@dataclass
class CacheEntry:
    data: Any
    expires_at: float


class ResponseCache:
    """
    LRU 内存缓存，TTL 过期。

    线程安全，适合单机使用。
    """

    def __init__(self, max_size: int = 256, default_ttl: int = DEFAULT_TTL_SECONDS):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    # ── Public API ───────────────────────────────────────

    def get(self, key: str) -> Any | None:
        """从缓存读取，未过期返回数据，过期返回 None"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None
            # LRU 提升
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.data

    def set(self, key: str, data: Any, ttl: int | None = None) -> None:
        """写入缓存"""
        with self._lock:
            ttl_seconds = ttl if ttl is not None else self._default_ttl
            self._cache[key] = CacheEntry(
                data=data,
                expires_at=time.monotonic() + ttl_seconds,
            )
            # LRU 淘汰
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        """删除指定缓存"""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, Any]:
        """返回缓存命中率统计"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "hit_rate": hit_rate,
        }

    # ── Key 生成 ───────────────────────────────────────

    @staticmethod
    def make_key(method: str, url: str, params: dict | None = None) -> str:
        """生成缓存键：method + url + sorted query params hash"""
        if params:
            param_str = "&".join(f"{k}={sorted(v) if isinstance(v, list) else v}" for k, v in sorted(params.items()))
            url = f"{url}?{param_str}"
        raw = f"{method.upper()}:{url}"
        return hashlib.sha1(raw.encode()).hexdigest()


# 全局单例
_response_cache: ResponseCache | None = None


def get_response_cache() -> ResponseCache:
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache
