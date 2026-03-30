#!/usr/bin/env python3
"""
eBay API 统一客户端
- Token 自动管理（Application Token 自动刷新 + User Token Refresh Token 续期）
- 请求重试（401 自动刷新 Token 后重试）
- 统一日志
- 沙盒/生产一键切换
"""

import json
import time
import base64
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("ebay_client")


class EbayClient:
    """eBay API 统一客户端"""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        self.config_path = Path(config_path)
        self.config = self._load_config()

        # 环境配置
        env = self.config.get("environment", "sandbox")
        self.env_config = self.config.get(env, {})
        self.api_base = self.env_config.get("api_base", "")
        self.web_base = self.env_config.get("web_base", "")

        # 市场配置
        mkt = self.config.get("marketplace", {})
        self.marketplace_id = mkt.get("marketplace_id", "EBAY_US")
        self.currency = mkt.get("currency", "USD")
        self.locale = mkt.get("locale", "en_US")

        # Token 缓存
        self._app_token = None
        self._app_token_expiry = None
        self._user_token = self.config.get("oauth", {}).get("user_token", "")
        self._user_token_expiry = None
        self._refresh_token = self.config.get("oauth", {}).get("refresh_token", "")

        # 业务策略
        policies = self.config.get("business_policies", {})
        self.payment_policy_id = policies.get("payment_policy_id", "")
        self.fulfillment_policy_id = policies.get("fulfillment_policy_id", "")
        self.return_policy_id = policies.get("return_policy_id", "")

        # 默认设置
        defaults = self.config.get("listing_defaults", {})
        self.auto_publish = defaults.get("auto_publish", False)
        self.default_condition = defaults.get("condition", "NEW")
        self.default_condition_id = defaults.get("condition_id", "1000")
        self.merchant_location_key = self.config.get("merchant_location_key", "")

        logger.info(f"eBay Client 初始化完成 | 环境: {env} | API: {self.api_base}")

    # ─── 配置 ───────────────────────────────────────────

    def _load_config(self):
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"配置文件未找到: {self.config_path}")
            raise

    def save_config(self):
        """保存配置（用于持久化 Refresh Token）"""
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        logger.info("配置已保存")

    # ─── Application Token（自动刷新，无需用户交互）───────

    def get_application_token(self):
        if self._app_token and self._app_token_expiry:
            if datetime.now() < self._app_token_expiry - timedelta(minutes=5):
                return self._app_token

        logger.info("获取 Application Token...")
        app_id = self.env_config.get("app_id", "")
        app_secret = self.env_config.get("app_secret", "")
        credentials = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

        resp = requests.post(
            f"{self.api_base}/identity/v1/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=30,
        )

        if resp.status_code != 200:
            logger.error(f"Application Token 获取失败: {resp.status_code} {resp.text[:200]}")
            return None

        data = resp.json()
        self._app_token = data["access_token"]
        self._app_token_expiry = datetime.now() + timedelta(
            seconds=data.get("expires_in", 7200)
        )
        logger.info(f"Application Token 获取成功, 过期: {self._app_token_expiry}")
        return self._app_token

    # ─── User Token（支持 Refresh Token 自动续期）────────

    def get_user_token(self):
        """获取 User Token，过期时尝试用 Refresh Token 续期"""
        # 如果有缓存且未过期
        if self._user_token and self._user_token_expiry:
            if datetime.now() < self._user_token_expiry - timedelta(minutes=5):
                return self._user_token

        # 如果有 Refresh Token，尝试续期
        if self._refresh_token:
            new_token = self._refresh_user_token()
            if new_token:
                return new_token

        # 直接使用配置中的 Token（可能是手动填入的）
        if self._user_token:
            return self._user_token

        logger.error(
            "User Token 未配置。请获取后填入 config.json 的 oauth.user_token"
        )
        return None

    def _refresh_user_token(self):
        """用 Refresh Token 获取新的 User Token"""
        logger.info("使用 Refresh Token 续期 User Token...")
        app_id = self.env_config.get("app_id", "")
        app_secret = self.env_config.get("app_secret", "")
        credentials = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

        scopes = self.config.get("oauth", {}).get("scopes", [])

        resp = requests.post(
            f"{self.api_base}/identity/v1/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "scope": " ".join(scopes),
            },
            timeout=30,
        )

        if resp.status_code != 200:
            logger.warning(f"Refresh Token 续期失败: {resp.status_code} — 可能需要重新授权")
            return None

        data = resp.json()
        self._user_token = data["access_token"]
        self._user_token_expiry = datetime.now() + timedelta(
            seconds=data.get("expires_in", 7200)
        )

        # 持久化新 Token
        self.config["oauth"]["user_token"] = self._user_token
        self.save_config()

        logger.info(f"User Token 续期成功, 过期: {self._user_token_expiry}")
        return self._user_token

    # ─── 统一请求方法 ──────────────────────────────────

    def _build_headers(self, use_user_token=True):
        token = self.get_user_token() if use_user_token else self.get_application_token()
        if not token:
            raise RuntimeError("无法获取有效 Token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
        }

    def request(self, method, path, data=None, use_user_token=True, retries=1):
        """
        统一 API 请求，自动处理 401 重试

        Args:
            method: HTTP 方法 (GET/POST/PUT/DELETE)
            path: API 路径，如 /sell/inventory/v1/inventory_item/SKU001
            data: 请求体 dict
            use_user_token: 是否使用 User Token
            retries: 401 重试次数

        Returns:
            ApiResponse 对象
        """
        url = f"{self.api_base}{path}"

        for attempt in range(retries + 1):
            try:
                headers = self._build_headers(use_user_token)
            except RuntimeError as e:
                return ApiResponse(0, None, {}, str(e))

            try:
                resp = requests.request(
                    method, url, headers=headers, json=data, timeout=60
                )
            except requests.RequestException as e:
                logger.error(f"请求异常: {e}")
                return ApiResponse(0, None, {}, str(e))

            # 成功
            if resp.status_code < 400:
                body = None
                if resp.text:
                    try:
                        body = resp.json()
                    except ValueError:
                        body = resp.text
                return ApiResponse(resp.status_code, body, dict(resp.headers), "")

            # 401: Token 过期，尝试刷新后重试
            if resp.status_code == 401 and attempt < retries:
                logger.warning("收到 401, 刷新 Token 后重试...")
                self._user_token_expiry = None  # 强制刷新
                self._app_token_expiry = None
                continue

            # 其他错误
            error_msg = resp.text[:500]
            logger.error(f"API 错误 {resp.status_code}: {error_msg}")
            body = None
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            return ApiResponse(resp.status_code, body, dict(resp.headers), error_msg)

    # ─── 便捷方法 ──────────────────────────────────────

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, data=None, **kwargs):
        return self.request("POST", path, data=data, **kwargs)

    def put(self, path, data=None, **kwargs):
        return self.request("PUT", path, data=data, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    # ─── 连接测试 ──────────────────────────────────────

    def test_connection(self):
        """测试 API 连接是否正常"""
        resp = self.get("/sell/inventory/v1/inventory_item?limit=1")
        if resp.ok:
            logger.info("API 连接测试成功")
            return True
        logger.error(f"API 连接测试失败: {resp.status_code}")
        return False


class ApiResponse:
    """API 响应封装"""

    def __init__(self, status_code, body, headers, error):
        self.status_code = status_code
        self.body = body
        self.headers = headers
        self.error = error

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    @property
    def offer_id(self):
        """从响应体或 Location header 提取 offer_id"""
        if isinstance(self.body, dict):
            oid = self.body.get("offerId", "")
            if oid:
                return oid
        location = self.headers.get("Location", "")
        if location:
            return location.rstrip("/").split("/")[-1]
        return ""

    @property
    def listing_id(self):
        if isinstance(self.body, dict):
            return self.body.get("listingId", "")
        return ""

    def __repr__(self):
        return f"<ApiResponse {self.status_code} ok={self.ok}>"
