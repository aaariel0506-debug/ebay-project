"""
modules/inventory_online/consistency_checker.py

Day 22: 库存一致性检测

定期对比线上 eBay 库存数量与线下实体库存数量。
不一致时发出 WARNING（不自动调整，需人工确认）。
"""

from dataclasses import dataclass

from loguru import logger as log


@dataclass
class InconsistencyItem:
    """单个 SKU 的库存不一致项。"""
    sku: str
    ebay_item_id: str | None
    ebay_quantity: int | None  # eBay 在线库存
    offline_quantity: int       # 线下实体库存
    difference: int             # ebay - offline（正=线上多，负=线上少）
    severity: str              # "warning" | "critical"


@dataclass
class ConsistencyReport:
    """一致性检测报告。"""
    total_checked: int
    inconsistent_count: int
    items: list[InconsistencyItem]
    all_consistent: bool

    def summary(self) -> str:
        if self.all_consistent:
            return (
                f"✅ 一致性检查通过\n"
                f"   共检查 {self.total_checked} 个 SKU，全部一致"
            )
        lines = [
            f"⚠️  发现 {self.inconsistent_count}/{self.total_checked} 个不一致："
        ]
        for item in self.items:
            lines.append(
                f"   [{item.severity.upper()}] {item.sku} | "
                f"eBay={item.ebay_quantity} | 线下={item.offline_quantity} | "
                f"差异={item.difference:+d}"
            )
        return "\n".join(lines)


class ConsistencyChecker:
    """线上 eBay 库存 vs 线下实体库存一致性检测。"""

    def __init__(self):
        from modules.inventory_offline import InboundService

        self._offline_svc = InboundService()

    def check(self, sku: str | None = None) -> ConsistencyReport:
        """
        检测库存一致性。

        Args:
            sku: 可选，只检查指定 SKU；None 则检查所有有 eBay listing 的 SKU

        Returns:
            ConsistencyReport
        """
        from core.database.connection import get_session
        from core.models import EbayListing

        inconsistencies: list[InconsistencyItem] = []

        with get_session() as sess:
            query = sess.query(EbayListing)
            if sku:
                query = query.filter(EbayListing.sku == sku)

            listings = query.all()
            checked = 0

            for listing in listings:
                checked += 1

                # 跳过无 ebay_item_id 的草稿 listing
                if not listing.ebay_item_id:
                    continue

                # 线下库存
                try:
                    stock_info = self._offline_svc.get_stock(listing.sku)
                    offline_qty = stock_info.get("available_quantity") or 0
                except Exception:
                    offline_qty = 0

                ebay_qty = listing.quantity_available or 0
                diff = ebay_qty - offline_qty

                # 阈值：|diff| > 0 即为不一致
                if diff != 0:
                    # critical：线上线下差距 ≥ 5，或线上为 0 但线下有货
                    severity = (
                        "critical"
                        if abs(diff) >= 5
                        or (ebay_qty == 0 and offline_qty > 0)
                        else "warning"
                    )
                    inconsistencies.append(InconsistencyItem(
                        sku=listing.sku,
                        ebay_item_id=listing.ebay_item_id,
                        ebay_quantity=ebay_qty,
                        offline_quantity=offline_qty,
                        difference=diff,
                        severity=severity,
                    ))

        report = ConsistencyReport(
            total_checked=checked,
            inconsistent_count=len(inconsistencies),
            items=inconsistencies,
            all_consistent=len(inconsistencies) == 0,
        )

        log.info(
            f"库存一致性检查：{checked} 个 SKU checked, "
            f"{len(inconsistencies)} 个不一致"
        )

        return report
