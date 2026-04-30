"""
modules/listing/variant_sku_syncer.py

从 EbayListing 表反向解析 variants JSON，在 products 表 upsert 子 SKU 记录。

 Brief 3 §T3 实现
 数据流：
   EbayListing（有 variants JSON）
     → 解析 variants
       → 父 SKU 不在 products 表 → 跳过，写 variant_sync_skipped.csv
       → 子 SKU 不存在 → 创建（parent_sku / variant_note 等）
       → 子 SKU 已存在 → 更新 parent_sku + variant_note（幂等）
 输出：
   ~/.ebay-project/imports/variant_sync_summary.txt
   ~/.ebay-project/imports/variant_sync_skipped.csv
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from core.database.connection import get_session
from core.models import EbayListing, Product, ProductStatus
from loguru import logger as log
from sqlalchemy import select

OUTPUT_DIR = Path.home() / ".ebay-project" / "imports"


# ── 结果 ──────────────────────────────────────────────────────────────────────

@dataclass
class SyncResult:
    """同步结果汇总。"""
    dry_run: bool = False
    listings_with_variants: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    # 每个跳过记录的详情 {sku, reason, parent_sku}
    skipped_detail: list[dict] = field(default_factory=list)
    # 每个错误详情 {listing_sku, error}
    error_detail: list[dict] = field(default_factory=list)
    summary_path: Optional[Path] = None
    skipped_path: Optional[Path] = None

    def summary(self) -> str:
        tag = "(--dry-run)" if self.dry_run else ""
        lines = [
            f"=== sync-variants-from-ebay {tag} ===",
            f"EbayListing 带 variants: {self.listings_with_variants} 条",
            f"  新建子 SKU: {self.created} 个",
            f"  更新子 SKU: {self.updated} 个",
            f"  跳过: {self.skipped} 个",
            f"  错误: {self.errors} 个",
        ]
        if self.skipped:
            lines.append("\n（详细写入 variant_sync_skipped.csv）")
        return "\n".join(lines)


# ── 解析 helpers ──────────────────────────────────────────────────────────────

def _parse_variant_note(aspects: dict[str, Any]) -> str:
    """将 aspects dict 拼成人类可读字符串，按 key 字典序排序。

    示例：{"Color": "Red", "Size": "M"} → "Color: Red, Size: M"
    空 dict → ""
    """
    if not aspects:
        return ""
    return ", ".join(f"{k}: {v}" for k, v in sorted(aspects.items()))


def _extract_variants_from_listing(listing: EbayListing) -> list[dict]:
    """从 EbayListing.variants JSON 提取所有子 SKU 和 aspects。

    支持两种格式（见 Brief §4.1）：
      格式 A: {"variantSKUs": [...], "aspects": {"SKU": {...}, ...}}
      格式 B: {"variations": [{"sku": "...", "aspects": {...}}, ...]}
      格式 C: 其他/空 → []

    TODO (Brief §4.1): 真实数据样本回来后补充 parser。
    在拿到真实 variants JSON 样本前，这里返回空列表。
    """
    raw = listing.variants
    if not raw or raw in ("{}", "null", "[]"):
        return []

    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        log.warning("EbayListing {} variants JSON 解析失败: {}", listing.sku, raw)
        return []

    # 格式 A: InventoryItemGroup 格式
    if "variantSKUs" in data and "aspects" in data:
        results = []
        for sku in data["variantSKUs"]:
            aspects = data["aspects"].get(sku, {})
            results.append({"sku": sku, "aspects": aspects})
        return results

    # 格式 B: 嵌套数组格式
    if "variations" in data:
        return [
            {"sku": v.get("sku"), "aspects": v.get("aspects", {})}
            for v in data["variations"]
            if v.get("sku")
        ]

    # 未知格式，记录但不 crash
    log.warning("EbayListing {} variants 格式未知: {}", listing.sku, list(data.keys()))
    return []


# ── 主类 ──────────────────────────────────────────────────────────────────────

class VariantSkuSyncer:
    def sync_from_ebay_listings(self, *, dry_run: bool = False) -> SyncResult:
        result = SyncResult(dry_run=dry_run)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        with get_session() as sess:
            # 拉所有有 variants 的 listing
            listings = sess.execute(
                select(EbayListing).where(
                    EbayListing.variants.isnot(None),
                    EbayListing.variants != "{}",
                    EbayListing.variants != "null",
                    EbayListing.variants != "[]",
                )
            ).scalars().all()

            result.listings_with_variants = len(listings)

            if not listings:
                log.info("EbayListing 没有带 variants 的记录")
                return result

            # 全量 product 拉入内存（按 sku 索引）
            all_products = {p.sku: p for p in sess.execute(select(Product)).scalars().all()}

            for listing in listings:
                variants = _extract_variants_from_listing(listing)
                for variant in variants:
                    child_sku = variant.get("sku")
                    if not child_sku:
                        continue

                    parent_sku = listing.sku
                    variant_note = _parse_variant_note(variant.get("aspects", {}))

                    # 路由：父 SKU 不在 products 表 → 跳过
                    if parent_sku not in all_products:
                        result.skipped += 1
                        result.skipped_detail.append({
                            "sku": child_sku,
                            "parent_sku": parent_sku,
                            "reason": f"父 SKU {parent_sku} 不在 products 表",
                        })
                        continue

                    if child_sku in all_products:
                        # 已存在：更新 parent_sku + variant_note（幂等）
                        if not dry_run:
                            p = all_products[child_sku]
                            p.parent_sku = parent_sku
                            p.variant_note = variant_note
                        result.updated += 1
                    else:
                        # 不存在：创建子 SKU
                        if not dry_run:
                            sess.add(Product(
                                sku=child_sku,
                                parent_sku=parent_sku,
                                variant_note=variant_note,
                                asin=None,
                                cost_price=None,
                                cost_currency="JPY",
                                supplier=None,
                                title=None,
                                source_url=None,
                                status=ProductStatus.ACTIVE,
                            ))
                            all_products[child_sku] = all_products.get(child_sku)  # placeholder
                        result.created += 1

        # 写报告
        result.skipped_path = self._write_skipped(result.skipped_detail)
        result.summary_path = self._write_summary(result)

        return result

    def _write_skipped(self, skipped: list[dict]) -> Path:
        path = OUTPUT_DIR / "variant_sync_skipped.csv"
        if skipped:
            pd.DataFrame(skipped).to_csv(path, index=False, encoding="utf-8")
        else:
            path.write_text("# (empty)\n", encoding="utf-8")
        return path

    def _write_summary(self, result: SyncResult) -> Path:
        path = OUTPUT_DIR / "variant_sync_summary.txt"
        path.write_text(result.summary(), encoding="utf-8")
        return path
