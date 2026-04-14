"""
core/ebay_api/rate_limit_config.py — eBay API 限流配置

各 API 的每日调用限额（eBay 官方文档值）。
格式：endpoint 前缀 -> 每日限额
"""
from typing import Final

# eBay API 每日限流值（不同 API 不同配额）
# 参考：https://developer.ebay.com/api-docs/common/rate-limits.html
RATE_LIMITS: Final[dict[str, int]] = {
    # Sell Inventory API
    "POST /sell/inventory/v1/inventory_item": 10000,
    "GET /sell/inventory/v1/inventory_item": 10000,
    "PUT /sell/inventory/v1/inventory_item": 10000,
    "DELETE /sell/inventory/v1/inventory_item": 10000,

    # Sell Fulfillment API
    "GET /sell/fulfillment/v1/order": 10000,
    "GET /sell/fulfillment/v1/order/": 10000,

    # Sell Account API
    "GET /sell/account/v1/": 5000,

    # Sell Finances API
    "GET /sell/finances/v1/": 5000,

    # Browse API（Application Token，限额通常较大）
    "GET /buy/browse/v1/": 5000,
    "GET /buy/deal/v1/": 5000,

    # Marketing API
    "GET /sell/marketing/v1/": 5000,
    "POST /sell/marketing/v1/": 5000,

    # 多用途匹配（未知 endpoint 用默认值）
}

# 全局限流默认值（未匹配到上述前缀时使用）
DEFAULT_DAILY_LIMIT: Final[int] = 5000
