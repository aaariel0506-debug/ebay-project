#!/usr/bin/env python3
"""
商品数据校验器
在调用 API 之前校验 Excel 数据的完整性和格式，提前发现问题
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("validator")

# 必填字段
REQUIRED_FIELDS = ["sku", "title", "description", "category_id", "price", "quantity", "image_urls"]

# eBay 标题最大长度
MAX_TITLE_LENGTH = 80

# 支持的 condition 值
VALID_CONDITIONS = {
    "NEW": "1000",
    "LIKE_NEW": "3000",
    "VERY_GOOD": "4000",
    "GOOD": "5000",
    "ACCEPTABLE": "6000",
    "FOR_PARTS_OR_NOT_WORKING": "7000",
}


@dataclass
class ValidationResult:
    """校验结果"""
    sku: str
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg):
        self.valid = False
        self.errors.append(msg)

    def add_warning(self, msg):
        self.warnings.append(msg)


def validate_item(row: dict) -> ValidationResult:
    """
    校验单个商品数据

    Args:
        row: Excel 行数据 (dict)

    Returns:
        ValidationResult
    """
    sku = str(row.get("sku", "")).strip()
    result = ValidationResult(sku=sku or "(empty)")

    # 1. 必填字段检查
    for field_name in REQUIRED_FIELDS:
        val = row.get(field_name)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            result.add_error(f"缺少必填字段: {field_name}")

    if not result.valid:
        return result  # 必填字段缺失，后续校验无意义

    # 2. SKU 格式（只允许字母、数字、下划线、连字符）
    import re
    if not re.match(r'^[A-Za-z0-9_\-]+$', sku):
        result.add_error(f"SKU 格式不合法 (只能包含字母/数字/下划线/连字符): {sku}")

    # 3. 标题长度
    title = str(row.get("title", "")).strip()
    if len(title) > MAX_TITLE_LENGTH:
        result.add_warning(f"标题超过 {MAX_TITLE_LENGTH} 字符 ({len(title)} 字), eBay 可能截断")

    if len(title) < 5:
        result.add_error("标题太短 (至少 5 个字符)")

    # 4. 价格
    try:
        price = float(row.get("price", 0))
        if price <= 0:
            result.add_error("价格必须大于 0")
        if price > 99999:
            result.add_warning(f"价格较高 (${price}), 请确认")
    except (ValueError, TypeError):
        result.add_error(f"价格格式不合法: {row.get('price')}")

    # 5. 数量
    try:
        qty = int(row.get("quantity", 0))
        if qty <= 0:
            result.add_error("数量必须大于 0")
    except (ValueError, TypeError):
        result.add_error(f"数量格式不合法: {row.get('quantity')}")

    # 6. 分类 ID
    try:
        cat_id = str(row.get("category_id", "")).strip()
        int(cat_id)  # 确保是数字
    except (ValueError, TypeError):
        result.add_error(f"分类 ID 不合法: {row.get('category_id')}")

    # 7. 图片 URL
    image_urls = str(row.get("image_urls", "")).strip()
    urls = [u.strip() for u in image_urls.split(",") if u.strip()]
    if len(urls) == 0:
        result.add_error("至少需要 1 张图片 URL")
    for url in urls:
        if not url.startswith("http"):
            result.add_error(f"图片 URL 格式不合法: {url}")

    # 8. Condition
    condition = str(row.get("condition", "NEW")).strip().upper()
    if condition and condition not in VALID_CONDITIONS:
        result.add_warning(
            f"condition '{condition}' 不在标准列表中, "
            f"有效值: {', '.join(VALID_CONDITIONS.keys())}"
        )

    # 9. 描述
    desc = str(row.get("description", "")).strip()
    if len(desc) < 20:
        result.add_warning("描述太短，建议至少 20 字符以提高 Listing 质量")

    return result


def validate_batch(rows: List[dict]) -> List[ValidationResult]:
    """批量校验"""
    results = []
    seen_skus = set()

    for i, row in enumerate(rows):
        result = validate_item(row)

        # 检查 SKU 重复
        if result.sku in seen_skus:
            result.add_error(f"SKU 重复: {result.sku}")
        seen_skus.add(result.sku)

        results.append(result)

    valid_count = sum(1 for r in results if r.valid)
    logger.info(f"校验完成: {valid_count}/{len(results)} 通过")
    for r in results:
        if not r.valid:
            logger.warning(f"  SKU {r.sku}: {'; '.join(r.errors)}")
        if r.warnings:
            logger.info(f"  SKU {r.sku} 警告: {'; '.join(r.warnings)}")

    return results
