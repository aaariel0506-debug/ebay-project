"""
core/ebay_api — eBay API 封装层

公开接口：
    ebay_auth   — OAuth 认证管理器（刷新 token、加密存储）
    ebay_client — 统一 HTTP 客户端（自动鉴权、重试、限流）
    异常类     — EbayApiError, EbayAuthError, EbayRateLimitError, ...
"""
from core.ebay_api.auth import EbayAuth, ebay_auth
from core.ebay_api.client import EbayClient, ebay_client
from core.ebay_api.exceptions import (
    EbayApiError,
    EbayAuthError,
    EbayNotFoundError,
    EbayRateLimitError,
    EbayServerError,
    EbayTokenMissingError,
)

__all__ = [
    "EbayAuth",
    "ebay_auth",
    "EbayClient",
    "ebay_client",
    "EbayApiError",
    "EbayAuthError",
    "EbayNotFoundError",
    "EbayRateLimitError",
    "EbayServerError",
    "EbayTokenMissingError",
]
