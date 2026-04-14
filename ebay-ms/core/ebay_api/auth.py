"""
core/ebay_api/auth.py — eBay Application Token (Client Credentials Flow)

使用 client_credentials 获取 Application Token。
- 自动缓存，过期前自动刷新
- Token 通过 keyring 加密存储（可选）
"""
import httpx
from datetime import datetime, timedelta, timezone
from core.config.settings import settings


# eBay OAuth scopes for application token
APPLICATION_SCOPES = "https://api.ebay.com/oauth/api_scope"


class EbayAuth:
    """
    eBay Application Token 管理器。

    使用 client_credentials flow 获取 App-level Token。
    Token 有效期 2 小时，自动缓存 + 提前刷新。
    """

    def __init__(self):
        self._token: str | None = None
        self._expires_at: datetime | None = None

    @property
    def api_base(self) -> str:
        """OAuth token endpoint"""
        if settings.EBAY_ENV == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    def _build_basic_auth(self) -> str:
        """Build Basic Auth header from APP_ID:CERT_ID"""
        import base64
        credentials = f"{settings.EBAY_APP_ID}:{settings.EBAY_CERT_ID}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def get_token(self, *, force_refresh: bool = False) -> str:
        """
        返回有效的 Application Token。

        内部自动缓存，过期前 5 分钟自动刷新。
        """
        if force_refresh:
            self._token = None
            self._expires_at = None

        # 缓存命中检查（提前 5 分钟刷新）
        if (
            self._token
            and self._expires_at
            and datetime.now(timezone.utc) < self._expires_at - timedelta(minutes=5)
        ):
            return self._token

        self._fetch_token()
        return self._token

    def _fetch_token(self) -> None:
        """调用 eBay OAuth endpoint 获取新 token"""
        url = f"{self.api_base}/identity/v1/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self._build_basic_auth(),
        }
        data = {
            "grant_type": "client_credentials",
            "scope": APPLICATION_SCOPES,
        }

        resp = httpx.post(url, headers=headers, data=data, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Application Token 获取失败 [{resp.status_code}]: {resp.text[:300]}"
            )

        body = resp.json()
        self._token = body["access_token"]
        expires_in = body.get("expires_in", 7200)
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    def get_headers(self) -> dict:
        """返回带 Bearer Token 的 HTTP 请求头"""
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def is_production(self) -> bool:
        return settings.EBAY_ENV == "production"


# 单例
ebay_auth = EbayAuth()
