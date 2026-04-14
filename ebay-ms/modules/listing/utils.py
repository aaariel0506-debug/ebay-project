"""modules.listing.utils — Listing 操作辅助函数"""
import re

# ── eBay 常量 ─────────────────────────────────────────────

EBAY_MARKETPLACE_IDS = {
    "US": "EBAY_US",
    "UK": "EBAY_GB",
    "DE": "EBAY_DE",
    "JP": "EBAY_JP",
    "AU": "EBAY_AU",
    "CA": "EBAY_CA",
}

EBAY_CONDITION_MAP = {
    "new": "NEW",
    "new_with_tags": "NEW_WITH_TAGS",
    "new_other": "NEW_OTHER",
    "very_good": "VERY_GOOD",
    "good": "GOOD",
    "acceptable": "ACCEPTABLE",
    "broken": "BREAKAGE",
}

EBAY_CONDITIONS = list(EBAY_CONDITION_MAP.values())


def normalize_condition(condition: str) -> str:
    """将用户友好的 condition 字符串转为 eBay 标准值"""
    condition = condition.strip().upper()
    if condition in EBAY_CONDITIONS:
        return condition
    mapped = EBAY_CONDITION_MAP.get(condition.lower())
    if mapped is None:
        raise ValueError(
            f"Invalid condition '{condition}'. "
            f"Allowed: {list(EBAY_CONDITION_MAP.keys())}"
        )
    return mapped


def format_price(amount: float, currency: str = "USD") -> str:
    """将金额格式化为字符串（eBay API 要求字符串格式）"""
    return f"{amount:.2f}"


def validate_image_urls(urls: list[str]) -> list[str]:
    """校验图片 URL 列表，返回有效 URL"""
    valid = []
    for url in urls:
        url = url.strip()
        if url.startswith("http://") or url.startswith("https://"):
            valid.append(url)
    return valid


def build_inventory_availability(quantity: int) -> dict:
    """构建 eBay Inventory API 的 availability 结构"""
    return {
        "shipToLocationAvailability": {
            "quantity": quantity,
        }
    }


def build_offers_pricing_summary(price: float, currency: str = "USD") -> dict:
    """构建 createOffer 的 pricingSummary 结构"""
    return {
        "price": {
            "currency": currency.upper(),
            "value": format_price(price),
        }
    }


def extract_listing_id_from_href(href: str | None) -> str | None:
    """从 listing href 中提取 listing ID"""
    if not href:
        return None
    match = re.search(r'/(\d+)(?:\?|$)', href)
    return match.group(1) if match else None
