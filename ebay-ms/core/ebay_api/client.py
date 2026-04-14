"""
core/ebay_api/client.py — eBay 统一 HTTP 客户端（生产级）

特性：
- 自动附加 Bearer Token（默认 User Token，可选 App Token）
- 401 自动刷新重试
- 429 指数退避 + 限流控制
- 5xx 重试（最多 3 次）+ 随机抖动
- GET 响应缓存（TTL 5 分钟）
- 离线降级模式（连续失败 3 次切 offline，操作写入 pending 队列）
- 请求计数持久化到 SQLite
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from core.config.settings import settings
from core.ebay_api.auth import ebay_auth
from core.ebay_api.cache import ResponseCache, get_response_cache
from core.ebay_api.exceptions import (
    EbayApiError,
    EbayAuthError,
    EbayNotFoundError,
    EbayRateLimitError,
    EbayServerError,
)
from core.ebay_api.rate_limiter import get_rate_limiter
from loguru import logger

_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 2
_OFFLINE_CONSECUTIVE_FAILURE_THRESHOLD = 3


# ── Offline Pending Queue ───────────────────────────────────

class PendingQueueStore:
    """Pending 操作持久化（SQLite）"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_pending_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    params TEXT,
                    json_body TEXT,
                    use_user_token INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )

    def enqueue(self, method: str, path: str, params: str | None, json_body: str | None, use_user_token: bool) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO api_pending_queue (method, path, params, json_body, use_user_token, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (method, path, params, json_body, int(use_user_token), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return cur.lastrowid

    def dequeue_all(self, limit: int = 50):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, method, path, params, json_body, use_user_token FROM api_pending_queue WHERE status='pending' ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return rows

    def mark_done(self, id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE api_pending_queue SET status='done' WHERE id=?", (id,))
            conn.commit()


class EbayClient:
    """
    eBay REST API 统一客户端（生产级）。

    用法::

        client = EbayClient()
        data = client.get("/sell/inventory/v1/inventory_item", params={"limit": 10})
        data = client.get("/buy/browse/v1/item_summary/search",
                         params={"q": "iPhone"}, use_user_token=False)
    """

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        marketplace_id: str = "EBAY_US",
        cache: ResponseCache | None = None,
    ):
        self._timeout = timeout
        self._marketplace_id = marketplace_id
        self._cache = cache or get_response_cache()
        self._rate_limiter = get_rate_limiter()
        self._pending_store = PendingQueueStore(settings.db_path.parent / "api_pending.db")

        self._is_online = True
        self._consecutive_failures = 0
        self._pending_lock = threading.Lock()
        self._startup_drain_pending()

    # ── 公开 HTTP 方法 ─────────────────────────────────

    def get(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("DELETE", path, **kwargs)

    # ── Online / Offline 状态 ─────────────────────────

    @property
    def is_online(self) -> bool:
        """当前是否在线"""
        return self._is_online

    def _go_offline(self):
        self._is_online = False
        logger.warning("EbayClient 切换为 OFFLINE 模式，API 操作将写入 pending 队列")

    def _go_online(self):
        if not self._is_online:
            self._is_online = True
            logger.info("EbayClient 恢复 ONLINE 模式，开始消化 pending 队列")
            self._drain_pending()

    def _startup_drain_pending(self):
        """启动时消化积压的 pending 操作"""
        rows = self._pending_store.dequeue_all(limit=50)
        if rows:
            logger.info("启动时发现 {} 条 pending API 操作待消化", len(rows))

    def _drain_pending(self):
        """消化 pending 队列"""
        rows = self._pending_store.dequeue_all(limit=20)
        for row in rows:
            id, method, path, params, json_body, use_user_token = row
            try:
                p = json.loads(params) if params else None
                b = json.loads(json_body) if json_body else None
                self._do_request(method, path, params=p, json_body=b, use_user_token=bool(use_user_token))
                self._pending_store.mark_done(id)
                logger.debug("pending 已处理: {} {}", method, path)
            except Exception:
                logger.warning("pending 处理失败 [{}]: {} {}", id, method, path)
                break  # 失败暂停，避免无限循环

    # ── 核心请求逻辑 ───────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
        use_user_token: bool = True,
        _from_pending: bool = False,
    ) -> dict[str, Any]:
        # ── 限流检查 ─────────────────────────────────
        try:
            self._rate_limiter.record(path)
        except EbayRateLimitError:
            raise

        # ── GET 缓存命中 ─────────────────────────────
        if method == "GET" and not _from_pending:
            cache_key = ResponseCache.make_key(method, path, params)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("CACHE HIT: {} {}", method, path)
                return cached

        # ── 在线请求 ─────────────────────────────────
        if self._is_online:
            try:
                result = self._do_request(method, path, params, json_body, headers, use_user_token)
                # 成功，恢复在线
                if self._consecutive_failures > 0:
                    self._go_online()
                if method == "GET" and result:
                    self._cache.set(cache_key, result)
                return result
            except EbayApiError:
                raise
            except Exception as exc:
                self._handle_failure(method, path, params, json_body, use_user_token)
                raise EbayApiError(f"请求异常: {exc}")

        # ── Offline 模式：入 pending 队列 ───────────
        return self._enqueue_pending(method, path, params, json_body, use_user_token)

    def _do_request(
        self,
        method: str,
        path: str,
        params: dict | None,
        json_body: dict | None,
        headers: dict | None = None,
        use_user_token: bool = True,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        url = f"{settings.ebay_api_url}{path}"
        req_headers = self._build_headers(headers, use_user_token)

        logger.debug("{} {} (retry={})", method, path, retry_count)

        try:
            resp = httpx.request(
                method, url, params=params, json=json_body,
                headers=req_headers, timeout=self._timeout,
            )
        except (OSError, IOError) as exc:
            return self._retry_or_raise(method, path, params, json_body, headers,
                                        use_user_token, retry_count, exc)

        return self._handle_response(resp, method, path, params, json_body,
                                     headers, use_user_token, retry_count)

    def _retry_or_raise(
        self, method: str, path: str, params, json_body, headers,
        use_user_token: bool, retry_count: int, exc: Exception
    ):
        if retry_count < _MAX_RETRIES:
            delay = (_BACKOFF_BASE ** retry_count) * (0.5 + (hash(str(exc)) % 100) / 100)
            logger.warning("网络错误，{}秒后重试 ({}/{}): {}", delay, retry_count + 1, _MAX_RETRIES, exc)
            time.sleep(delay)
            return self._do_request(method, path, params, json_body, headers,
                                    use_user_token, retry_count + 1)
        raise EbayApiError(f"网络请求失败: {exc}") from exc

    def _handle_response(
        self, resp: httpx.Response,
        method: str, path: str, params, json_body,
        headers, use_user_token: bool, retry_count: int,
    ) -> dict[str, Any]:
        status = resp.status_code

        # 2xx 成功
        if 200 <= status < 300:
            if status == 204 or not resp.text.strip():
                return {}
            return resp.json()

        # 401 → 刷新 token 重试
        if status == 401:
            if retry_count == 0:
                logger.warning("收到 401，刷新 token 后重试")
                if use_user_token:
                    ebay_auth.get_user_token(force_refresh=True)
                else:
                    ebay_auth.get_app_token(force_refresh=True)
                return self._do_request(method, path, params, json_body, headers,
                                        use_user_token, retry_count + 1)
            raise EbayAuthError(f"认证失败（已重试）: {path}", status_code=status, response_body=resp.text)

        # 404
        if status == 404:
            raise EbayNotFoundError(f"资源不存在: {path}", status_code=status, response_body=resp.text)

        # 429 → 退避重试
        if status == 429:
            retry_after = int(resp.headers.get("Retry-After", _BACKOFF_BASE ** retry_count))
            if retry_count < _MAX_RETRIES:
                logger.warning("限流 429，{}秒后重试 ({}/{})", retry_after, retry_count + 1, _MAX_RETRIES)
                time.sleep(retry_after)
                return self._do_request(method, path, params, json_body, headers,
                                        use_user_token, retry_count + 1)
            raise EbayRateLimitError(f"限流未恢复: {path}", retry_after=retry_after,
                                     status_code=status, response_body=resp.text)

        # 5xx → 重试
        if status >= 500:
            if retry_count < _MAX_RETRIES:
                delay = (_BACKOFF_BASE ** retry_count) * (0.5 + (status % 50) / 100)
                logger.warning("服务器错误 [{}]，{}秒后重试 ({}/{})", status, delay, retry_count + 1, _MAX_RETRIES)
                time.sleep(delay)
                return self._do_request(method, path, params, json_body, headers,
                                        use_user_token, retry_count + 1)
            raise EbayServerError(f"服务器持续错误: {path}", status_code=status, response_body=resp.text)

        # 其他 4xx
        raise EbayApiError(f"请求失败 [{status}]: {path}", status_code=status, response_body=resp.text)

    # ── 离线降级 ─────────────────────────────────────

    def _handle_failure(
        self, method: str, path: str, params, json_body, use_user_token: bool
    ):
        self._consecutive_failures += 1
        if self._consecutive_failures >= _OFFLINE_CONSECUTIVE_FAILURE_THRESHOLD:
            self._go_offline()
        self._enqueue_pending(method, path, params, json_body, use_user_token)

    def _enqueue_pending(
        self, method: str, path: str, params, json_body, use_user_token: bool
    ) -> dict[str, Any]:
        with self._pending_lock:
            id = self._pending_store.enqueue(
                method=method,
                path=path,
                params=json.dumps(params) if params else None,
                json_body=json.dumps(json_body) if json_body else None,
                use_user_token=use_user_token,
            )
            logger.debug("操作写入 pending 队列: {} {} (id={})", method, path, id)
            return {"_pending": True, "id": id, "queued_at": datetime.now(timezone.utc).isoformat()}

    # ── 辅助 ──────────────────────────────────────────

    def _build_headers(
        self, extra: dict | None = None, use_user_token: bool = True
    ) -> dict[str, str]:
        token = ebay_auth.get_user_token() if use_user_token else ebay_auth.get_app_token()
        h = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": self._marketplace_id,
        }
        if extra:
            h.update(extra)
        return h

    def clear_cache(self):
        """手动清除响应缓存"""
        self._cache.clear()


# 全局单例
ebay_client = EbayClient()
