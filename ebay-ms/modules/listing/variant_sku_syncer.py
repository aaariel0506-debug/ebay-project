"""
modules/listing/variant_sku_syncer.py

从 order_items 订单数据反向推导变体父子关系，写入 products 表。

数据源：order_items.sku 含下划线的子 SKU（如 01-2509-0002_Da）
数据源：order_items.sku 不含下划线 → 不是变体，跳过

父子关系推导：
  子 SKU 01-2509-0002_Da → 父 SKU = 01-2509-0002（下划线最后一段为颜色/尺寸后缀）
  颜色示例：_Da(深色), _Wh(白), _Em(翡翠), _RED, _BLUE
  尺寸示例：_S, _M, _L, _XL
  variant_note = 后缀的人类可读翻译（如 "_Da" → "Color: Dark"）

路由：
  父 SKU 不在 products 表 → 跳过，写 variant_sync_skipped.csv
  子 SKU 不存在 → 创建（parent_sku / variant_note 等）
  子 SKU 已存在 → 更新 parent_sku + variant_note（幂等）

Brief 3 §T3
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
from core.database.connection import get_session
from core.models import OrderItem, Product, ProductStatus
from loguru import logger as log
from sqlalchemy import select

OUTPUT_DIR = Path.home() / ".ebay-project" / "imports"


# ── 结果 ──────────────────────────────────────────────────────────────────────

@dataclass
class SyncResult:
    """同步结果汇总。"""
    dry_run: bool = False
    child_skus_found: int = 0   # order_items 里找到的子 SKU 总数
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    skipped_detail: list[dict] = field(default_factory=list)
    error_detail: list[dict] = field(default_factory=list)
    summary_path: Optional[Path] = None
    skipped_path: Optional[Path] = None

    def summary(self) -> str:
        tag = "(--dry-run)" if self.dry_run else ""
        lines = [
            f"=== sync-variants-from-ebay {tag} ===",
            f"order_items 子 SKU（含下划线）: {self.child_skus_found} 个",
            f"  新建子 SKU: {self.created} 个",
            f"  更新子 SKU: {self.updated} 个",
            f"  跳过: {self.skipped} 个",
            f"  错误: {self.errors} 个",
        ]
        if self.skipped:
            lines.append("\n（详细写入 variant_sync_skipped.csv）")
        return "\n".join(lines)


# ── 下划线后缀 → variant_note ───────────────────────────────────────────────

_VARIANT_SUFFIX_MAP = {
    "Da": "Color: Dark",
    "Wh": "Color: White",
    "Em": "Color: Emerald",
    "RED": "Color: Red",
    "BLUE": "Color: Blue",
    "GREEN": "Color: Green",
    "BLACK": "Color: Black",
    "PK": "Color: Pink",
    "S": "Size: S",
    "M": "Size: M",
    "L": "Size: L",
    "XL": "Size: XL",
    "XXL": "Size: XXL",
    "SET": "Type: Set",
    "04": "Size: 04",
    "06": "Size: 06",
    "08": "Size: 08",
}


def _suffix_from_sku(sku: str) -> str:
    """提取 SKU 最后一段下划线后缀。"""
    if "_" not in sku:
        return ""
    return sku.split("_")[-1]


def _parent_sku_from_child(child_sku: str) -> str:
    """从子 SKU 反推父 SKU：去掉最后一个下划线后缀。"""
    if "_" not in child_sku:
        return child_sku
    parts = child_sku.rsplit("_", 1)
    return parts[0]


def _build_variant_note(suffix: str) -> str:
    """将下划线后缀转为人类可读 variant_note。"""
    known = _VARIANT_SUFFIX_MAP.get(suffix)
    if known:
        return known
    # 未知后缀：直接用原始后缀
    return f"Variant: {suffix}"


# ── 主类 ──────────────────────────────────────────────────────────────────────

class VariantSkuSyncer:
    def sync_from_order_items(self, *, dry_run: bool = False) -> SyncResult:
        """从 order_items 里的子 SKU（下划线模式）反向推导父子关系，upsert 到 products。"""
        result = SyncResult(dry_run=dry_run)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        with get_session() as sess:
            # 拉所有含下划线的子 SKU（去重）
            rows = sess.execute(
                select(OrderItem.sku)
                .distinct()
            ).scalars().all()

            # 过滤：只取含下划线的 SKU（Python 层二次过滤，防止 SQL LIKE escape 不一致）
            child_skus = list({s for s in rows if "_" in s})
            result.child_skus_found = len(child_skus)

            if not child_skus:
                log.info("order_items 没有含下划线的子 SKU")
                return result

            # 全量 product 拉入内存（按 sku 索引）
            all_products = {p.sku: p for p in sess.execute(select(Product)).scalars().all()}
            all_parent_skus = set(all_products.keys())

            for child_sku in child_skus:
                parent_candidate = _parent_sku_from_child(child_sku)
                suffix = _suffix_from_sku(child_sku)
                variant_note = _build_variant_note(suffix)

                # 路由：父 SKU 不在 products 表 → 跳过
                if parent_candidate not in all_parent_skus:
                    result.skipped += 1
                    result.skipped_detail.append({
                        "sku": child_sku,
                        "parent_sku": parent_candidate,
                        "reason": f"父 SKU {parent_candidate} 不在 products 表",
                    })
                    continue

                if child_sku in all_products:
                    # 已存在：更新 parent_sku + variant_note（幂等）
                    if not dry_run:
                        p = all_products[child_sku]
                        p.parent_sku = parent_candidate
                        p.variant_note = variant_note
                        result.updated += 1
                else:
                    # 不存在：创建子 SKU
                    if not dry_run:
                        sess.add(Product(
                            sku=child_sku,
                            parent_sku=parent_candidate,
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

    # 兼容 Brief §T3 的旧接口名
    def sync_from_ebay_listings(self, *, dry_run: bool = False) -> SyncResult:
        """兼容别名：实际从 order_items 拉数据（eBay API 无变体数据）。"""
        return self.sync_from_order_items(dry_run=dry_run)

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
