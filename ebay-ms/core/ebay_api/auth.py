"""
core/ebay_api/auth.py — eBay OAuth 2.0 认证管理

支持两种 Token：
1. Application Token (client_credentials) — 公共 API（Browse 等）
2. User Token (refresh_token) — 卖家 API（Sell Inventory/Account/Fulfillment 等）
"""
import base64
import time

import httpx
from core.config.settings import settings
from core.ebay_api.exceptions import EbayAuthError, EbayTokenMissingError
from core.security.token_store import token_store
from loguru import logger

# ── Scope 常量 ────────────────────────────────────────────
APPLICATION_SCOPES = "https://api.ebay.com/oauth/api_scope"

USER_SCOPES = (
    "https://api.ebay.com/oauth/api_scope "
    "https://api.ebay.com/oauth/api_scope/sell.inventory "
    "https://api.ebay.com/oauth/api_scope/sell.marketing "
    "https://api.ebay.com/oauth/api_scope/sell.account "
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment"
)

# ── token_store key 名 ───────────────────────────────────
_KEY_REFRESH = "ebay_refresh_token"
_KEY_USER_ACCESS = "ebay_user_access_token"
_KEY_USER_EXPIRES = "ebay_user_token_expires_at"

# 提前 5 分钟视为过期
_EXPIRY_BUFFER_SECONDS = 300


class EbayAuth:
    """
    eBay OAuth 2.0 管理器。

    用法：
        auth = EbayAuth()

        # 卖家操作（Sell API）→ User Token
        auth.store_refresh_token("v^1.1#i^1#r^1#...")
        user_token = auth.get_user_token()

        # 公共查询（Browse API）→ Application Token
        app_token = auth.get_app_token()
    """

    def __init__(self):
        # User Token 缓存
        self._user_token: str | None = None
        self._user_expires_at: float = 0.0
        # Application Token 缓存
        self._app_token: str | None = None
        self._app_expires_at: float = 0.0

        self._load_cached_user_token()

    # ══════════════════════════════════════════════════════
    # User Token（refresh_token flow）— 卖家 API 专用
    # ══════════════════════════════════════════════════════

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

    def get_user_token(self, force_refresh: bool = False) -> str:
        """
        获取 User Access Token（卖家操作用）。
        过期或 force_refresh 时自动用 refresh_token 刷新。
        """
        if not force_refresh and self._user_token and time.time() < self._user_expires_at:
            return self._user_token

        logger.info("User token 过期或缺失，开始刷新…")
        self._refresh_user_token()
        return self._user_token

    # 向后兼容
    get_access_token = get_user_token

    def _refresh_user_token(self) -> None:
        """用 refresh_token 换取新的 User Access Token"""
        refresh_token = self.get_refresh_token()

        resp = self._call_oauth({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": USER_SCOPES,
        })

        self._user_token = resp["access_token"]
        expires_in = int(resp.get("expires_in", 7200))
        self._user_expires_at = time.time() + expires_in - _EXPIRY_BUFFER_SECONDS

        # 持久化
        token_store.save_token(_KEY_USER_ACCESS, self._user_token)
        token_store.save_token(_KEY_USER_EXPIRES, str(self._user_expires_at))
        logger.info("User token 刷新成功，有效期 {} 秒", expires_in)

    def _load_cached_user_token(self) -> None:
        """启动时从 keyring 加载已缓存的 user token"""
        cached = token_store.get_token(_KEY_USER_ACCESS)
        expires_str = token_store.get_token(_KEY_USER_EXPIRES)
        if cached and expires_str:
            try:
                self._user_expires_at = float(expires_str)
                if time.time() < self._user_expires_at:
                    self._user_token = cached
                    logger.debug("已加载缓存的 user token")
            except (ValueError, TypeError):
                pass

    # ══════════════════════════════════════════════════════
    # Application Token（client_credentials flow）— 公共 API
    # ══════════════════════════════════════════════════════

    def get_app_token(self, force_refresh: bool = False) -> str:
        """
        获取 Application Token（公共 API 用）。
        过期或 force_refresh 时自动刷新。
        """
        if not force_refresh and self._app_token and time.time() < self._app_expires_at:
            return self._app_token

        logger.info("Application token 过期或缺失，开始获取…")
        self._fetch_app_token()
        return self._app_token

    # 向后兼容 UM870 的 get_token
    get_token = get_app_token

    def _fetch_app_token(self) -> None:
        """用 client_credentials 获取 Application Token"""
        resp = self._call_oauth({
            "grant_type": "client_credentials",
            "scope": APPLICATION_SCOPES,
        })

        self._app_token = resp["access_token"]
        expires_in = int(resp.get("expires_in", 7200))
        self._app_expires_at = time.time() + expires_in - _EXPIRY_BUFFER_SECONDS
        logger.info("Application token 获取成功，有效期 {} 秒", expires_in)

    # ══════════════════════════════════════════════════════
    # 公共工具
    # ══════════════════════════════════════════════════════

    def get_headers(self, use_user_token: bool = True) -> dict[str, str]:
        """返回带 Bearer Token 的请求头"""
        token = self.get_user_token() if use_user_token else self.get_app_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def clear_tokens(self) -> None:
        """清除所有已存储的 token"""
        for key in (_KEY_REFRESH, _KEY_USER_ACCESS, _KEY_USER_EXPIRES):
            token_store.delete_token(key)
        self._user_token = None
        self._user_expires_at = 0.0
        self._app_token = None
        self._app_expires_at = 0.0
        logger.info("所有 eBay token 已清除")

    def _call_oauth(self, body: dict) -> dict:
        """调用 eBay OAuth endpoint 的公共方法"""
        credentials = f"{settings.EBAY_APP_ID}:{settings.EBAY_CERT_ID}"
        b64_creds = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {b64_creds}",
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
                f"OAuth 失败 [{resp.status_code}]: {resp.text[:300]}",
                status_code=resp.status_code,
                response_body=resp.text,
            )

        return resp.json()


# 全局单例
ebay_auth = EbayAuth()
