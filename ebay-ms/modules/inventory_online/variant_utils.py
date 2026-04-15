"""
变体级别库存解析工具（Day 15）。

从 EbayListing.variants JSON 中解析变体维度（Size、Color 等），
支持按维度筛选缺货/低库存变体。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VariantStock:
    """单个变体的库存状态。"""
    sku: str
    ebay_item_id: str | None
    variant_specifics: dict[str, str]  # {"Size": "M", "Color": "Red"}
    quantity: int
    price: float | None
    status: str  # NORMAL | LOW_STOCK | OUT_OF_STOCK

    @property
    def is_out_of_stock(self) -> bool:
        return self.quantity == 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.quantity <= 2

    @property
    def display_name(self) -> str:
        """如 'Size: M / Color: Red'"""
        parts = [f"{k}: {v}" for k, v in self.variant_specifics.items()]
        return " / ".join(parts)


@dataclass
class VariantGroupStock:
    """一个变体组的库存汇总。"""
    group_id: str | None
    parent_title: str | None
    variant_count: int
    skus: list[str]
    variants: list[VariantStock]
    aggregate_status: str  # NORMAL | PARTIAL_OUT_OF_STOCK | FULLY_OUT_OF_STOCK

    @property
    def total_quantity(self) -> int:
        return sum(v.quantity for v in self.variants)

    @property
    def out_of_stock_count(self) -> int:
        return sum(1 for v in self.variants if v.is_out_of_stock)

    @property
    def low_stock_count(self) -> int:
        return sum(1 for v in self.variants if v.is_low_stock)

    def out_of_stock_skus(self) -> list[str]:
        return [v.sku for v in self.variants if v.is_out_of_stock]

    def low_stock_skus(self) -> list[str]:
        return [v.sku for v in self.variants if v.is_low_stock]


def parse_variants_from_json(variants_json: dict | None) -> dict[str, str]:
    """从 EbayListing.variants JSON 中提取 variant_specifics 字典。"""
    if not variants_json:
        return {}
    return variants_json.get("variant_specifics", {})


def group_variants(listings: list) -> list[VariantGroupStock]:
    """将一组 EbayListing 按 group_id 分组，聚合为 VariantGroupStock。

    listings 中的每条记录必须包含 variants JSON 字段（包含 group_id 和 siblings）。
    """
    from collections import defaultdict

    groups: dict[str, list] = defaultdict(list)

    for listing in listings:
        variants_json = getattr(listing, "variants", None) or {}
        group_id = variants_json.get("group_id") or getattr(listing, "sku", None)

        vs = parse_variants_from_json(variants_json)
        qty = getattr(listing, "quantity_available", 0) or 0
        price = getattr(listing, "listing_price", None)

        if qty == 0:
            status = "OUT_OF_STOCK"
        elif qty <= 2:
            status = "LOW_STOCK"
        else:
            status = "NORMAL"

        variant_stock = VariantStock(
            sku=getattr(listing, "sku", ""),
            ebay_item_id=getattr(listing, "ebay_item_id", None),
            variant_specifics=vs,
            quantity=qty,
            price=float(price) if price else None,
            status=status,
        )
        groups[group_id].append(variant_stock)

    result: list[VariantGroupStock] = []
    for group_id, variant_list in groups.items():
        # 从第一条记录获取组级别信息
        first = variant_list[0]
        # parent_title extracted from first variant_stock variant_specifics dict key

        total = len(variant_list)
        oos = sum(1 for v in variant_list if v.is_out_of_stock)
        low = sum(1 for v in variant_list if v.is_low_stock)

        if oos == total:
            agg_status = "FULLY_OUT_OF_STOCK"
        elif oos > 0 or low > 0:
            agg_status = "PARTIAL_OUT_OF_STOCK"
        else:
            agg_status = "NORMAL"

        result.append(VariantGroupStock(
            group_id=group_id,
            parent_title=first.variant_specifics.get("_parent_title") or first.variant_specifics.get("parent_title"),
            variant_count=total,
            skus=[v.sku for v in variant_list],
            variants=variant_list,
            aggregate_status=agg_status,
        ))

    return result


def list_variants_by_filter(
    listings: list,
    filter_dimension: str | None = None,
    filter_value: str | None = None,
) -> list[VariantStock]:
    """按变体维度筛选（如找出所有 Size=L 的变体）。

    Args:
        listings: EbayListing 列表
        filter_dimension: 维度名称（如 "Size"）
        filter_value: 维度值（如 "L"）

    Returns:
        符合条件的 VariantStock 列表
    """
    results: list[VariantStock] = []
    for listing in listings:
        vs = parse_variants_from_json(getattr(listing, "variants", None))
        if vs and filter_dimension and filter_value:
            if vs.get(filter_dimension) != filter_value:
                continue

        qty = getattr(listing, "quantity_available", 0) or 0
        price = getattr(listing, "listing_price", None)
        if qty == 0:
            status = "OUT_OF_STOCK"
        elif qty <= 2:
            status = "LOW_STOCK"
        else:
            status = "NORMAL"

        results.append(VariantStock(
            sku=getattr(listing, "sku", ""),
            ebay_item_id=getattr(listing, "ebay_item_id", None),
            variant_specifics=vs,
            quantity=qty,
            price=float(price) if price else None,
            status=status,
        ))

    return results
