"""
core/ebay_api/auth.py
eBay OAuth 2.0 认证管理
- 用 refresh_token 刷新 access_token
- 与 token_store 集成，加密持久化
- 带过期跟踪，自动续期
"""
import base64
import time

import httpx
from core.config.settings import settings
from core.ebay_api.exceptions import EbayAuthError, EbayTokenMissingError
from core.security.token_store import token_store
from loguru import logger

# token_store 中的 key 名
_KEY_REFRESH = "ebay_refresh_token"
_KEY_ACCESS = "ebay_access_token"
_KEY_EXPIRES = "ebay_token_expires_at"

# 提前 5 分钟视为过期，避免边界竞态
_EXPIRY_BUFFER_SECONDS = 300


class EbayAuth:
    """
    eBay OAuth 2.0 管理器。

    用法：
        auth = EbayAuth()
        auth.store_refresh_token("v^1.1#i^1#r^1#...")
        token = auth.get_access_token()   # 自动刷新
    """

    def __init__(self):
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._load_cached_token()

    # ── 公开方法 ──────────────────────────────────────────

    def store_refresh_token(self, refresh_token: str) -> None:
        """安全存储 refresh_token（加密写入 keyring）"""
        token_store.save_token(_KEY_REFRESH, refresh_token)
        logger.info("Refresh token 已安全存储")

    def get_refresh_token(self) -> str:
        """读取已存储的 refresh_token"""
        rt = token_store.get_token(_KEY_REFRESH)
        if not rt:
            raise EbayTokenMissingError(
                "Refresh token 未找到。请先调用 store_refresh_token() 或检查 keyring 配置。"
            )
        return rt

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        获取有效的 access_token。
        如果 token 已过期或 force_refresh=True，自动用 refresh_token 刷新。
        """
        if not force_refresh and self._access_token and time.time() < self._expires_at:
            return self._access_token

        logger.info("Access token 过期或缺失，开始刷新…")
        self._refresh()
        return self._access_token

    def clear_tokens(self) -> None:
        """清除所有已存储的 token"""
        for key in (_KEY_REFRESH, _KEY_ACCESS, _KEY_EXPIRES):
            token_store.delete_token(key)
        self._access_token = None
        self._expires_at = 0.0
        logger.info("所有 eBay token 已清除")

    # ── 内部方法 ──────────────────────────────────────────

    def _load_cached_token(self) -> None:
        """启动时从 keyring 加载已缓存的 access_token（如未过期）"""
        cached = token_store.get_token(_KEY_ACCESS)
        expires_str = token_store.get_token(_KEY_EXPIRES)
        if cached and expires_str:
            try:
                self._expires_at = float(expires_str)
                if time.time() < self._expires_at:
                    self._access_token = cached
                    logger.debug("已加载缓存的 access_token（有效期至 {}）", self._expires_at)
            except (ValueError, TypeError):
                pass

    def _refresh(self) -> None:
        """用 refresh_token 向 eBay 换取新的 access_token"""
        refresh_token = self.get_refresh_token()

        # Basic auth = base64(APP_ID:CERT_ID)
        credentials = f"{settings.EBAY_APP_ID}:{settings.EBAY_CERT_ID}"
        b64_creds = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {b64_creds}",
        }
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope "
                     "https://api.ebay.com/oauth/api_scope/sell.inventory "
                     "https://api.ebay.com/oauth/api_scope/sell.marketing "
                     "https://api.ebay.com/oauth/api_scope/sell.account "
                     "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
        }

        try:
            resp = httpx.post(
                settings.ebay_oauth_url,
                headers=headers,
                data=body,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise EbayAuthError(f"OAuth 请求网络错误: {exc}") from exc

        if resp.status_code != 200:
            raise EbayAuthError(
                f"OAuth 刷新失败 [{resp.status_code}]",
                status_code=resp.status_code,
                response_body=resp.text,
            )

        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 7200))
        self._expires_at = time.time() + expires_in - _EXPIRY_BUFFER_SECONDS

        # 持久化到 keyring
        token_store.save_token(_KEY_ACCESS, self._access_token)
        token_store.save_token(_KEY_EXPIRES, str(self._expires_at))

        logger.info("Access token 刷新成功，有效期 {} 秒", expires_in)


# 全局单例
ebay_auth = EbayAuth()
