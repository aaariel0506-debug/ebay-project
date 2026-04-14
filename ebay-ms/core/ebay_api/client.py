"""
core/ebay_api/client.py — eBay 统一 HTTP 客户端

- 自动附加 Bearer token（默认 User Token，可选 App Token）
- 401 自动刷新重试
- 429 指数退避
- 5xx 重试（最多 3 次）
- 统一日志 + Marketplace ID
"""
import time
from typing import Any

import httpx
from core.config.settings import settings
from core.ebay_api.auth import ebay_auth
from core.ebay_api.exceptions import (
    EbayApiError,
    EbayAuthError,
    EbayNotFoundError,
    EbayRateLimitError,
    EbayServerError,
)
from loguru import logger

_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 2


class EbayClient:
    """
    eBay REST API 统一客户端。

    用法：
        client = EbayClient()
        # 卖家 API（默认用 User Token）
        data = client.get("/sell/inventory/v1/inventory_item", params={"limit": 10})
        # 公共 API（用 Application Token）
        data = client.get("/buy/browse/v1/item_summary/search",
                          params={"q": "iPhone"}, use_user_token=False)
    """

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        marketplace_id: str = "EBAY_US",
    ):
        self._timeout = timeout
        self._marketplace_id = marketplace_id

    # ── 公开 HTTP 方法 ───────────────────────────────────

    def get(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("DELETE", path, **kwargs)

    # ── 核心请求逻辑 ─────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
        use_user_token: bool = True,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        url = f"{settings.ebay_api_url}{path}"
        req_headers = self._build_headers(headers, use_user_token)

        logger.debug("{} {} (retry={})", method, path, retry_count)

        try:
            resp = httpx.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=req_headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            if retry_count < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** retry_count
                logger.warning("网络错误，{}秒后重试 ({}/{}): {}", wait, retry_count + 1, _MAX_RETRIES, exc)
                time.sleep(wait)
                return self._request(method, path, params=params, json_body=json_body,
                                     headers=headers, use_user_token=use_user_token,
                                     retry_count=retry_count + 1)
            raise EbayApiError(f"网络请求失败: {exc}") from exc

        return self._handle_response(resp, method, path, params, json_body, headers,
                                     use_user_token, retry_count)

    def _handle_response(
        self,
        resp: httpx.Response,
        method: str,
        path: str,
        params: dict | None,
        json_body: dict | None,
        headers: dict | None,
        use_user_token: bool,
        retry_count: int,
    ) -> dict[str, Any]:
        status = resp.status_code

        # 成功
        if 200 <= status < 300:
            if status == 204 or not resp.text.strip():
                return {}
            return resp.json()

        # 401 → 刷新 token 重试一次
        if status == 401:
            if retry_count == 0:
                logger.warning("收到 401，尝试刷新 token 后重试")
                if use_user_token:
                    ebay_auth.get_user_token(force_refresh=True)
                else:
                    ebay_auth.get_app_token(force_refresh=True)
                return self._request(method, path, params=params, json_body=json_body,
                                     headers=headers, use_user_token=use_user_token,
                                     retry_count=retry_count + 1)
            raise EbayAuthError(
                f"认证失败 (已重试): {path}",
                status_code=status,
                response_body=resp.text,
            )

        # 404
        if status == 404:
            raise EbayNotFoundError(
                f"资源不存在: {path}",
                status_code=status,
                response_body=resp.text,
            )

        # 429 → 退避重试
        if status == 429:
            retry_after = int(resp.headers.get("Retry-After", _BACKOFF_BASE ** retry_count))
            if retry_count < _MAX_RETRIES:
                logger.warning("触发限流，等待 {}秒后重试 ({}/{})", retry_after, retry_count + 1, _MAX_RETRIES)
                time.sleep(retry_after)
                return self._request(method, path, params=params, json_body=json_body,
                                     headers=headers, use_user_token=use_user_token,
                                     retry_count=retry_count + 1)
            raise EbayRateLimitError(
                f"限流未恢复: {path}",
                retry_after=retry_after,
                status_code=status,
                response_body=resp.text,
            )

        # 5xx → 重试
        if status >= 500:
            if retry_count < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** retry_count
                logger.warning("服务器错误 [{}]，{}秒后重试 ({}/{})", status, wait, retry_count + 1, _MAX_RETRIES)
                time.sleep(wait)
                return self._request(method, path, params=params, json_body=json_body,
                                     headers=headers, use_user_token=use_user_token,
                                     retry_count=retry_count + 1)
            raise EbayServerError(
                f"服务器持续错误: {path}",
                status_code=status,
                response_body=resp.text,
            )

        # 其他 4xx
        raise EbayApiError(
            f"请求失败 [{status}]: {path}",
            status_code=status,
            response_body=resp.text,
        )

    def _build_headers(self, extra: dict | None = None, use_user_token: bool = True) -> dict[str, str]:
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


# 全局单例
ebay_client = EbayClient()
