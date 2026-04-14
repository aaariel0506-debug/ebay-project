"""
tests/test_ebay_api.py
Day 3 — eBay API 封装层单元测试

测试覆盖：
  1. 异常层级关系
  2. OAuth 刷新成功 → access_token 返回
  3. OAuth 刷新失败 → 抛 EbayAuthError
  4. refresh_token 缺失 → 抛 EbayTokenMissingError
  5. client GET 200 → 返回 JSON
  6. client 401 → 自动刷新重试
  7. client 429 → 退避重试
  8. client 404 → EbayNotFoundError
  9. client 500 → EbayServerError（重试耗尽后）
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
    """异常继承关系 + 属性"""

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
    """OAuth 刷新逻辑（mock HTTP + token_store）"""

    def _make_auth(self):
        """创建干净的 EbayAuth 实例（不触发 keyring 加载）"""
        with patch("core.ebay_api.auth.token_store") as mock_store:
            mock_store.get_token.return_value = None
            from core.ebay_api.auth import EbayAuth
            auth = EbayAuth()
        return auth

    def test_refresh_success(self):
        auth = self._make_auth()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "v^1.1#new_token",
            "expires_in": 7200,
            "token_type": "User Access Token",
        }

        with (
            patch("core.ebay_api.auth.token_store") as mock_store,
            patch("core.ebay_api.auth.httpx.post", return_value=mock_resp),
        ):
            mock_store.get_token.side_effect = lambda key: {
                "ebay_refresh_token": "v^1.1#refresh_xxx",
                "ebay_access_token": None,
                "ebay_token_expires_at": None,
            }.get(key)

            token = auth.get_access_token(force_refresh=True)

        assert token == "v^1.1#new_token"
        # 验证 token 被持久化
        assert mock_store.save_token.call_count == 2  # access + expires

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
            with pytest.raises(EbayAuthError, match="OAuth 刷新失败"):
                auth.get_access_token(force_refresh=True)

    def test_missing_refresh_token_raises(self):
        auth = self._make_auth()

        with patch("core.ebay_api.auth.token_store") as mock_store:
            mock_store.get_token.return_value = None
            with pytest.raises(EbayTokenMissingError, match="Refresh token 未找到"):
                auth.get_access_token()

    def test_cached_token_reused(self):
        """未过期的 access_token 直接返回，不发 HTTP"""
        auth = self._make_auth()
        auth._access_token = "cached_token"
        auth._expires_at = time.time() + 3600  # 1 小时后才过期

        # 不 mock httpx —— 如果代码发了请求会报错
        token = auth.get_access_token()
        assert token == "cached_token"


# ── Client 测试 ───────────────────────────────────────────


class TestEbayClient:
    """HTTP 客户端逻辑（mock auth + httpx）"""

    def _make_client(self):
        from core.ebay_api.client import EbayClient
        return EbayClient(timeout=5.0)

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_get_200(self, mock_request, mock_auth):
        mock_auth.get_access_token.return_value = "test_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"items":[]}'
        mock_resp.json.return_value = {"items": []}
        mock_request.return_value = mock_resp

        client = self._make_client()
        result = client.get("/sell/inventory/v1/inventory_item", params={"limit": 10})

        assert result == {"items": []}
        # 验证 Bearer header
        call_kwargs = mock_request.call_args
        assert "Bearer test_token" in call_kwargs.kwargs["headers"]["Authorization"]

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_401_triggers_refresh(self, mock_request, mock_auth):
        mock_auth.get_access_token.return_value = "refreshed_token"

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
        mock_auth.get_access_token.assert_any_call(force_refresh=True)

    @patch("core.ebay_api.client.time.sleep")  # 避免真等
    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_429_retries(self, mock_request, mock_auth, mock_sleep):
        mock_auth.get_access_token.return_value = "token"

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
        mock_auth.get_access_token.return_value = "token"

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
        mock_auth.get_access_token.return_value = "token"

        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.text = "Internal Server Error"
        # 4 次都是 500（初始 + 3 次重试）
        mock_request.return_value = resp_500

        client = self._make_client()
        with pytest.raises(EbayServerError):
            client.get("/broken")

        # 验证重试了 3 次
        assert mock_sleep.call_count == 3

    @patch("core.ebay_api.client.ebay_auth")
    @patch("core.ebay_api.client.httpx.request")
    def test_204_returns_empty(self, mock_request, mock_auth):
        mock_auth.get_access_token.return_value = "token"

        resp = MagicMock()
        resp.status_code = 204
        resp.text = ""
        mock_request.return_value = resp

        client = self._make_client()
        result = client.delete("/some-resource")
        assert result == {}
