"""modules.listing.utils — Listing 操作辅助函数"""
import re
from typing import Any

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


# ── Variant Listing 辅助 ─────────────────────────────────────

def build_inventory_item_group(body: dict) -> dict:
    """
    构建 eBay Inventory Item Group 的 body 结构。
    参考：POST /sell/inventory/v1/inventory_item_group
    """
    group: dict[str, Any] = {}

    if body.get("group_title"):
        group["groupTitle"] = body["group_title"]
    if body.get("group_description"):
        group["groupDescription"] = body["group_description"]
    if body.get("brand"):
        group["brand"] = body["brand"]
    if body.get("category_id"):
        group["categoryId"] = body["category_id"]

    # 图片
    if body.get("image_urls"):
        group["imageUrls"] = body["image_urls"]

    # 变体 specifics
    variants = body.get("variants", [])
    if variants:
        vs_list = []
        for v in variants:
            for spec in v.get("variant_specifics", []):
                vs_list.append({"name": spec["name"], "value": spec["value"]})
        # 去重
        seen: set[tuple] = set()
        unique: list[dict] = []
        for item in vs_list:
            key = (item["name"], item["value"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        group["variantSpecificsSet"] = {"variantSpecifics": unique}

    return group


def build_variant_payload(
    sku: str,
    price: float,
    quantity: int,
    condition: str,
    variant_specifics: list[dict],
    image_urls: list[str],
    currency: str = "USD",
) -> dict:
    """
    为单个变体构建 createOrReplaceInventoryItem 请求体。
    包含 product_reference 引用 group。
    """
    payload: dict[str, Any] = {
        "sku": sku,
        "availability": build_inventory_availability(quantity),
        "condition": condition,
        "pricingSummary": {
            "pricingInformations": [
                {
                    "pricing": {
                        "price": {
                            "currency": currency.upper(),
                            "value": format_price(price),
                        }
                    }
                }
            ]
        },
        "product": {
            "references": [
                {
                    "marketplaceId": "EBAY_US",
                    "productIdentifier": {"productId": sku},
                    "productIdType": "SKU",
                }
            ]
        },
        "conditionConditionValues": [
            {"conditionId": condition, "conditionDescription": "Seller refurbished"}
        ],
    }

    if image_urls:
        payload["imageUrls"] = image_urls[:12]

    if variant_specifics:
        payload["variantSpecifics"] = variant_specifics

    return payload


# ── 图片校验 ─────────────────────────────────────────────────

ALLOWED_IMAGE_FORMATS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_IMAGE_SIZE_BYTES = 7 * 1024 * 1024  # 7 MB per image (eBay 限制)


def validate_image_files(
    paths: list[str],
) -> tuple[list[str], list[dict]]:
    """
    校验本地图片文件。
    - 检查文件是否存在
    - 检查扩展名是否为允许格式
    - 检查文件大小是否 ≤ 7MB

    Returns:
        (valid_urls, validation_results)
        valid_urls: 可用于 eBay pictureUrls 的 file:// URL 列表
        validation_results: 每张图片的校验详情
    """
    from pathlib import Path

    valid: list[str] = []
    results: list[dict] = []

    for path in paths:
        path = path.strip()
        result: dict[str, Any] = {"path": path, "valid": False, "error": None}

        # 检查是否为 URL
        if path.startswith("http://") or path.startswith("https://"):
            # URL 直接通过（格式和大小校验需外部工具，这里做格式后缀检查）
            ext = Path(path).suffix.lower().lstrip(".")
            if ext in ALLOWED_IMAGE_FORMATS:
                result["valid"] = True
                result["format"] = ext
                result["size_bytes"] = None  # URL 无法本地检查
                valid.append(path)
            else:
                result["error"] = f"URL 扩展名 '{ext}' 不在允许列表 {ALLOWED_IMAGE_FORMATS}"
            results.append(result)
            continue

        # 本地文件路径
        file_path = Path(path)
        if not file_path.is_file():
            result["error"] = "文件不存在"
            results.append(result)
            continue

        size = file_path.stat().st_size
        result["size_bytes"] = size

        ext = file_path.suffix.lower().lstrip(".")
        result["format"] = ext

        if ext not in ALLOWED_IMAGE_FORMATS:
            result["error"] = f"格式 '{ext}' 不在允许列表 {ALLOWED_IMAGE_FORMATS}"
            results.append(result)
            continue

        if size > MAX_IMAGE_SIZE_BYTES:
            result["error"] = f"文件大小 {size / 1024 / 1024:.1f}MB 超过 7MB 限制"
            results.append(result)
            continue

        result["valid"] = True
        valid.append(f"file://{file_path.resolve()}")
        results.append(result)

    return valid, results
