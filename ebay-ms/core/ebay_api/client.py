"""
core/ebay_api/client.py — eBay API Async HTTP Client

基于 httpx.AsyncClient 的异步 eBay API 客户端。
- 自动注入 Bearer Token
- 401 自动重试（Token 刷新后）
- 统一错误处理
"""
from __future__ import annotations

import httpx
from typing import Any
from core.config.settings import settings
from core.ebay_api.auth import ebay_auth


class EbayApiError(Exception):
    """API 错误异常"""

    def __init__(self, status_code: int, body: Any, message: str = ""):
        self.status_code = status_code
        self.body = body
        self.message = message or f"API error {status_code}"
        super().__init__(self.message)


class EbayClient:
    """
    异步 eBay API 客户端。

    用法示例::

        async with EbayClient() as client:
            resp = await client.get("/sell/inventory/v1/inventory_item/SKU001")
            if resp.is_success:
                print(resp.data)
            else:
                print(resp.error)
    """

    def __init__(
        self,
        *,
        marketplace_id: str = "EBAY_US",
        timeout: float = 60.0,
    ):
        self.marketplace_id = marketplace_id
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def api_base(self) -> str:
        if settings.EBAY_ENV == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _build_headers(self) -> dict:
        headers = ebay_auth.get_headers()
        headers["X-EBAY-C-MARKETPLACE-ID"] = self.marketplace_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict | None = None,
        retries: int = 1,
    ) -> ApiResponse:
        """
        统一请求方法，自动处理 401 重试。

        Args:
            method: HTTP 方法
            path: API 路径，如 /sell/inventory/v1/inventory_item/SKU001
            data: 请求体 dict
            retries: 401 重试次数

        Returns:
            ApiResponse 对象
        """
        if not self._client:
            raise RuntimeError("EbayClient must be used as async context manager")

        for attempt in range(retries + 1):
            headers = self._build_headers()

            try:
                resp = await self._client.request(
                    method=method,
                    url=path,
                    headers=headers,
                    json=data,
                )
            except httpx.RequestError as e:
                return ApiResponse(success=False, status_code=0, data=None, error=str(e))

            # 2xx 成功
            if resp.status_code < 400:
                body = None
                if resp.text:
                    try:
                        body = resp.json()
                    except ValueError:
                        body = resp.text
                return ApiResponse(
                    success=True,
                    status_code=resp.status_code,
                    data=body,
                    error="",
                )

            # 401: Token 过期，强制刷新后重试
            if resp.status_code == 401 and attempt < retries:
                ebay_auth.get_token(force_refresh=True)
                continue

            # 其他错误
            error_body = None
            try:
                error_body = resp.json()
            except ValueError:
                error_body = resp.text
            return ApiResponse(
                success=False,
                status_code=resp.status_code,
                data=error_body,
                error=str(error_body)[:300],
            )

    # ── 便捷方法 ──────────────────────────────────────

    async def get(self, path: str, **kwargs) -> ApiResponse:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, data: dict | None = None, **kwargs) -> ApiResponse:
        return await self._request("POST", path, data=data, **kwargs)

    async def put(self, path: str, data: dict | None = None, **kwargs) -> ApiResponse:
        return await self._request("PUT", path, data=data, **kwargs)

    async def delete(self, path: str, **kwargs) -> ApiResponse:
        return await self._request("DELETE", path, **kwargs)

    # ── 连接测试 ──────────────────────────────────────

    async def test_connection(self) -> bool:
        """测试 API 连接（用 application token 读库存）"""
        resp = await self.get("/sell/inventory/v1/inventory_item?limit=1")
        return resp.success


class ApiResponse:
    """API 响应封装"""

    def __init__(
        self,
        success: bool,
        status_code: int,
        data: Any,
        error: str,
    ):
        self.success = success
        self.status_code = status_code
        self.data = data
        self.error = error

    @property
    def is_success(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        return f"<ApiResponse {self.status_code} success={self.success}>"
