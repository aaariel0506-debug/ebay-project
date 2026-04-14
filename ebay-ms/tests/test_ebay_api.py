"""
tests/test_ebay_api.py
Day 3 — eBay API 封装层单元测试

测试覆盖：
  异常类 3 个 + Auth 5 个 + Client 6 个 = 14 个测试
"""
import time
from unittest.mock import MagicMock, patch

import pytest
from core.ebay_api.exceptions import (
    EbayApiError,
    EbayAuthError,
    EbayNotFoundError,
    EbayRateLimitError,
    EbayServerError,
    EbayTokenMissingError,
)

# ── 异常测试 ──────────────────────────────────────────────


class TestExceptions:

    def test_hierarchy(self):
        assert issubclass(EbayAuthError, EbayApiError)
        assert issubclass(EbayRateLimitError, EbayApiError)
        assert issubclass(EbayNotFoundError, EbayApiError)
        assert issubclass(EbayServerError, EbayApiError)
        assert issubclass(EbayTokenMissingError, EbayAuthError)

    def test_api_error_attributes(self):
        err = EbayApiError("bad", status_code=400, response_body='{"error":"x"}')
        assert err.status_code == 400
        assert "x" in err.response_body

    def test_rate_limit_retry_after(self):
        err = EbayRateLimitError("slow", retry_after=60, status_code=429)
        assert err.retry_after == 60


# ── Auth 测试 ─────────────────────────────────────────────


class TestEbayAuth:

    def _make_auth(self):
        """创建干净的 EbayAuth 实例"""
        with patch("core.ebay_api.auth.token_store") as mock_store:
            mock_store.get_token.return_value = None
            from core.ebay_api.auth import EbayAuth
            auth = EbayAuth()
        return auth

    def test_user_token_refresh_success(self):
        auth = self._make_auth()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "v^1.1#new_user_token",
            "expires_in": 7200,
        }

        with (
            patch("core.ebay_api.auth.token_store") as mock_store,
            patch("core.ebay_api.auth.httpx.post", return_value=mock_resp),
        ):
            mock_store.get_token.side_effect = lambda key: {
                "ebay_refresh_token": "v^1.1#refresh_xxx",
            }.get(key)

            token = auth.get_user_token(force_refresh=True)

        assert token == "v^1.1#new_user_token"
        assert mock_store.save_token.call_count == 2  # access + expires

    def test_app_token_success(self):
        auth = self._make_auth()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "v^1.1#app_token",
            "expires_in": 7200,
        }

        with patch("core.ebay_api.auth.httpx.post", return_value=mock_resp):
            token = auth.get_app_token()

        assert token == "v^1.1#app_token"

    def test_refresh_failure_raises(self):
        auth = self._make_auth()

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"error":"invalid_grant"}'

        with (
            patch("core.ebay_api.auth.token_store") as mock_store,
            patch("core.ebay_api.auth.httpx.post", return_value=mock_resp),
        ):
            mock_store.get_token.side_effect = lambda key: (
                "v^1.1#old_refresh" if key == "ebay_refresh_token" else None
            )
            with pytest.raises(EbayAuthError, match="OAuth 失败"):
                auth.get_user_token(force_refresh=True)

    def test_missing_refresh_token_raises(self):
        auth = self._make_auth()

        with patch("core.ebay_api.auth.token_store") as mock_store:
            mock_store.get_token.return_value = None
            with pytest.raises(EbayTokenMissingError, match="Refresh token 未找到"):
                auth.get_user_token()

    def test_cached_token_reused(self):
        auth = self._make_auth()
        auth._user_token = "cached_token"
        auth._user_expires_at = time.time() + 3600

        token = auth.get_user_token()
        assert token == "cached_token"


# ── Client 测试 ───────────────────────────────────────────



class TestEbayClient:

    def _make_client(self):
        """用 __new__ 创建 + 干净缓存实例，绕过全局单例状态"""
        import threading

        from core.ebay_api.cache import ResponseCache
        from core.ebay_api.client import EbayClient

        c = EbayClient.__new__(EbayClient)
        c._timeout = 5.0
        c._marketplace_id = "EBAY_US"
        c._cache = ResponseCache(default_ttl=60)  # 独立干净实例，stats 从零开始
        c._rate_limiter = MagicMock()
        c._pending_store = MagicMock()
        c._is_online = True
        c._consecutive_failures = 0
        c._pending_lock = threading.RLock()
        return c

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_get_200(self, mock_request, mock_auth):
        mock_auth.get_user_token.return_value = "test_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"items":[]}'
        mock_resp.json.return_value = {"items": []}
        mock_request.return_value = mock_resp

        client = self._make_client()
        result = client.get("/sell/inventory/v1/inventory_item", params={"limit": 10})

        assert result == {"items": []}
        call_kwargs = mock_request.call_args
        assert "Bearer test_token" in call_kwargs.kwargs["headers"]["Authorization"]

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_401_triggers_refresh(self, mock_request, mock_auth):
        mock_auth.get_user_token.return_value = "refreshed_token"

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.text = "Unauthorized"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.text = '{"ok":true}'
        resp_200.json.return_value = {"ok": True}

        mock_request.side_effect = [resp_401, resp_200]

        client = self._make_client()
        result = client.get("/test")

        assert result == {"ok": True}
        mock_auth.get_user_token.assert_any_call(force_refresh=True)

    @patch("core.ebay_api.client.time.sleep")
    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_429_retries(self, mock_request, mock_auth, mock_sleep):
        mock_auth.get_user_token.return_value = "token"

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1"}
        resp_429.text = "Rate limited"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.text = '{"ok":true}'
        resp_200.json.return_value = {"ok": True}

        mock_request.side_effect = [resp_429, resp_200]

        client = self._make_client()
        result = client.get("/test")

        assert result == {"ok": True}
        mock_sleep.assert_called_once_with(1)

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_404_raises(self, mock_request, mock_auth):
        mock_auth.get_user_token.return_value = "token"

        resp = MagicMock()
        resp.status_code = 404
        resp.text = "Not Found"
        mock_request.return_value = resp

        client = self._make_client()
        with pytest.raises(EbayNotFoundError):
            client.get("/nonexistent")

    @patch("core.ebay_api.client.time.sleep")
    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_500_retries_then_raises(self, mock_request, mock_auth, mock_sleep):
        mock_auth.get_user_token.return_value = "token"

        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.text = "Internal Server Error"
        mock_request.return_value = resp_500

        client = self._make_client()
        with pytest.raises(EbayServerError):
            client.get("/broken")

        assert mock_sleep.call_count == 3

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_204_returns_empty(self, mock_request, mock_auth):
        mock_auth.get_user_token.return_value = "token"

        resp = MagicMock()
        resp.status_code = 204
        resp.text = ""
        mock_request.return_value = resp

        client = self._make_client()
        result = client.delete("/some-resource")
        assert result == {}


