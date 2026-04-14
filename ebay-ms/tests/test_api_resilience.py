"""
tests/test_api_resilience.py — API 弹性测试套件

覆盖：
1. 重试机制（网络超时 / 5xx）
2. 限流（80% 警告 / 95% 拒绝）
3. 缓存命中
4. 离线降级模式
"""
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.ebay_api.cache import ResponseCache
from core.ebay_api.exceptions import EbayRateLimitError
from core.ebay_api.rate_limiter import RateLimiter, RateLimitStore

# ── 1. 重试机制测试 ─────────────────────────────────────

def test_retry_on_network_error():
    """网络错误应重试 3 次后抛出"""
    from core.ebay_api import client
    attempts = {"count": 0}

    def fake_request(*args, **kwargs):
        attempts["count"] += 1
        raise OSError("connection refused")

    with patch.object(client.httpx, "request", fake_request):
        with patch.object(client.ebay_auth, "get_user_token", return_value="fake_token"):
            c = client.EbayClient.__new__(client.EbayClient)
            c._timeout = 5.0
            c._marketplace_id = "EBAY_US"
            c._cache = client.get_response_cache()
            c._rate_limiter = MagicMock()
            c._rate_limiter.record.return_value = 1
            c._pending_store = MagicMock()
            c._is_online = True
            c._consecutive_failures = 0
            c._pending_lock = __import__("threading").RLock()

            with pytest.raises(client.EbayApiError):
                c._do_request("GET", "/test/path", None, None)

    assert attempts["count"] == 4  # 1 initial + 3 retries


def test_no_retry_on_4xx():
    """4xx 错误不应重试，直接抛出"""
    from core.ebay_api import client

    fake_resp = MagicMock()
    fake_resp.status_code = 400
    fake_resp.text = '{"error": "bad request"}'

    call_count = {"count": 0}

    def fake_request(*args, **kwargs):
        call_count["count"] += 1
        return fake_resp

    with patch.object(client.httpx, "request", fake_request):
        with patch.object(client.ebay_auth, "get_user_token", return_value="fake_token"):
            c = client.EbayClient.__new__(client.EbayClient)
            c._timeout = 5.0
            c._marketplace_id = "EBAY_US"
            c._cache = client.get_response_cache()
            c._rate_limiter = MagicMock()
            c._rate_limiter.record.return_value = 1
            c._pending_store = MagicMock()
            c._is_online = True
            c._consecutive_failures = 0
            c._pending_lock = __import__("threading").RLock()

            with pytest.raises(client.EbayApiError):
                c._do_request("GET", "/test/path", None, None)

    assert call_count["count"] == 1  # 无重试


# ── 2. 限流测试 ─────────────────────────────────────────

def test_rate_limiter_reject_at_95_percent():
    """达到 95% 限额应抛 EbayRateLimitError"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    s = RateLimitStore(db_path)
    s._ensure_table()

    # 直接插入今天的计数（达到 95%）
    today = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d")
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO rate_counts VALUES ('GET /sell/test', ?, 950)", (today,))
        conn.commit()

    limiter = RateLimiter(s)
    limiter._limits = {"GET /sell/test": 1000}

    with pytest.raises(EbayRateLimitError):
        limiter.check("GET /sell/test")

    Path(tmp.name).unlink()


# ── 3. 缓存测试 ─────────────────────────────────────────

def test_cache_hit_returns_cached_data():
    """第二次相同 GET 应从缓存返回"""
    cache = ResponseCache(max_size=10, default_ttl=60)
    cache.set("key1", {"result": "data"})
    result = cache.get("key1")
    assert result == {"result": "data"}


def test_cache_miss_returns_none_for_expired():
    """TTL 过期应返回 None"""
    cache = ResponseCache(max_size=10, default_ttl=1)
    cache.set("key2", {"result": "expired"})
    time.sleep(1.1)
    result = cache.get("key2")
    assert result is None


def test_cache_key_is_deterministic():
    """相同 method+url+params 应生成相同 key"""
    k1 = ResponseCache.make_key("GET", "/api/test", {"a": 1, "b": 2})
    k2 = ResponseCache.make_key("GET", "/api/test", {"b": 2, "a": 1})
    assert k1 == k2


def test_cache_key_differs_by_method():
    """GET 和 POST 相同 URL 应生成不同 key"""
    k1 = ResponseCache.make_key("GET", "/api/test", None)
    k2 = ResponseCache.make_key("POST", "/api/test", None)
    assert k1 != k2


def test_cache_stats():
    """缓存命中率统计"""
    # Use fresh instance to avoid singleton state
    cache = ResponseCache(default_ttl=60)
    cache.get("nonexistent")  # miss
    cache.set("key", {"v": 1})
    cache.get("key")  # hit
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5


# ── 4. 离线降级测试 ─────────────────────────────────────

def test_offline_after_3_consecutive_failures():
    """连续 3 次 _handle_failure 调用应切换 offline 模式"""
    from core.ebay_api import client

    c = client.EbayClient.__new__(client.EbayClient)
    c._is_online = True
    c._consecutive_failures = 0
    c._pending_store = MagicMock()
    c._pending_lock = __import__("threading").RLock()

    # 模拟 3 次失败（不触发真正的 HTTP 请求）
    c._handle_failure("GET", "/test", None, None, True)
    assert c._consecutive_failures == 1
    assert c._is_online is True

    c._handle_failure("GET", "/test", None, None, True)
    assert c._consecutive_failures == 2
    assert c._is_online is True

    c._handle_failure("GET", "/test", None, None, True)
    # 第 3 次失败应触发 offline
    assert c._consecutive_failures == 3
    assert c._is_online is False


def test_offline_request_goes_to_pending_queue():
    """Offline 模式下请求应写入 pending 队列"""
    from core.ebay_api import client

    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.text = "Service Unavailable"

    with patch.object(client.httpx, "request", return_value=fake_resp):
        with patch.object(client.ebay_auth, "get_user_token", return_value="fake_token"):
            c = client.EbayClient.__new__(client.EbayClient)
            c._timeout = 5.0
            c._marketplace_id = "EBAY_US"
            c._cache = client.get_response_cache()
            c._rate_limiter = MagicMock()
            c._rate_limiter.record.return_value = 1
            c._pending_store = MagicMock()
            c._pending_store.enqueue.return_value = 42
            c._is_online = False  # already offline
            c._consecutive_failures = 3
            c._pending_lock = __import__("threading").RLock()

            result = c._request("POST", "/test/path", json_body={"sku": "A1"}, use_user_token=True)

    assert result["_pending"] is True
    assert result["id"] == 42
    c._pending_store.enqueue.assert_called_once()


def test_cache_clear():
    """手动清除缓存"""
    # Use fresh instance to avoid singleton state
    from core.ebay_api.cache import ResponseCache
    cache = ResponseCache(default_ttl=60)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    # Verify stats after hit
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0
    # Clear should reset counters
    cache.clear()
    stats_after = cache.stats()
    assert stats_after["hits"] == 0
    assert stats_after["misses"] == 0
    assert stats_after["size"] == 0
