"""
Day 14: 库存监控 + 缺货预警

- InventoryMonitor：库存状态查询
- list_out_of_stock()：缺货商品（quantity=0）
- list_low_stock(threshold)：低库存商品
- 自动 STOCK_ALERT 事件发布
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger as log

if TYPE_CHECKING:
    from core.ebay_api.client import EbayClient


DEFAULT_LOW_STOCK_THRESHOLD = 2


@dataclass
class StockStatus:
    """单个商品的库存状态。"""
    sku: str
    ebay_item_id: str | None
    title: str | None
    quantity: int
    listing_price: float | None
    status: str  # NORMAL | LOW_STOCK | OUT_OF_STOCK | ENDED
    variants: dict | None = None

    @property
    def is_out_of_stock(self) -> bool:
        return self.quantity == 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.quantity <= DEFAULT_LOW_STOCK_THRESHOLD


class InventoryMonitor:
    """库存监控服务。"""

    def __init__(self, client: EbayClient | None = None):
        from core.ebay_api.client import EbayClient
        self.client = client or EbayClient()

    def list_all(self, limit: int = 100, offset: int = 0) -> list[StockStatus]:
        """列出所有商品的库存状态。

        Returns:
            list[StockStatus]：库存快照列表。
        """
        from core.database.connection import get_session
        from core.models import EbayListing

        with get_session() as sess:
            q = sess.query(EbayListing).order_by(EbayListing.sku)
            q = q.offset(offset).limit(limit)
            listings = q.all()
            return [self._to_stock_status(listing_) for listing_ in listings]

    def list_out_of_stock(self) -> list[StockStatus]:
        """列出所有缺货商品（quantity=0）。"""
        from core.database.connection import get_session
        from core.models import EbayListing, ListingStatus

        with get_session() as sess:
            listings = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ACTIVE,
                EbayListing.quantity_available == 0,
            ).all()
            return [self._to_stock_status(listing_) for listing_ in listings]

    def list_low_stock(self, threshold: int = DEFAULT_LOW_STOCK_THRESHOLD) -> list[StockStatus]:
        """列出低库存商品（0 < quantity <= threshold）。"""
        from core.database.connection import get_session
        from core.models import EbayListing, ListingStatus

        with get_session() as sess:
            listings = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ACTIVE,
                EbayListing.quantity_available > 0,
                EbayListing.quantity_available <= threshold,
            ).all()
            return [self._to_stock_status(listing_) for listing_ in listings]

    def check_and_alert(self, threshold: int = DEFAULT_LOW_STOCK_THRESHOLD) -> list[StockStatus]:
        """检查缺货/低库存并发布 STOCK_ALERT 事件。

        在 SyncService.full_sync() 之后调用，确保同步后触发检查。

        Returns:
            list[StockStatus]：触发预警的商品列表。
        """
        from modules.inventory_online.sync_service import SyncService

        # 从 eBay 实时拉取最新库存（不走 DB 缓存）
        SyncService(client=self.client).full_sync()

        # 再从 DB 读取状态
        out_of_stock = self.list_out_of_stock()
        low_stock = self.list_low_stock(threshold)
        alerts = out_of_stock + low_stock

        if alerts:
            self._publish_stock_alerts(out_of_stock, low_stock)

        return alerts

    def _publish_stock_alerts(
        self,
        out_of_stock: list[StockStatus],
        low_stock: list[StockStatus],
    ) -> None:
        """发布 STOCK_ALERT 事件。"""
        from core.events.bus import EventBus

        bus = EventBus()

        if out_of_stock:
            bus.publish(
                event_type="STOCK_ALERT",
                payload={
                    "alert_type": "OUT_OF_STOCK",
                    "skus": [s.sku for s in out_of_stock],
                    "count": len(out_of_stock),
                    "list": [
                        {"sku": s.sku, "title": s.title, "quantity": s.quantity}
                        for s in out_of_stock
                    ],
                },
            )
            log.warning(f"STOCK_ALERT: {len(out_of_stock)} 件缺货 — {[s.sku for s in out_of_stock]}")

        if low_stock:
            bus.publish(
                event_type="STOCK_ALERT",
                payload={
                    "alert_type": "LOW_STOCK",
                    "skus": [s.sku for s in low_stock],
                    "count": len(low_stock),
                    "list": [
                        {"sku": s.sku, "title": s.title, "quantity": s.quantity}
                        for s in low_stock
                    ],
                },
            )
            log.warning(f"LOW_STOCK_ALERT: {len(low_stock)} 件低库存 — {[s.sku for s in low_stock]}")

    def _to_stock_status(self, listing) -> StockStatus:
        """将 EbayListing ORM 对象转为 StockStatus。"""

        qty = listing.quantity_available or 0
        if listing.status.name == "ENDED":
            status = "ENDED"
        elif qty == 0:
            status = "OUT_OF_STOCK"
        elif qty <= DEFAULT_LOW_STOCK_THRESHOLD:
            status = "LOW_STOCK"
        else:
            status = "NORMAL"

        return StockStatus(
            sku=listing.sku,
            ebay_item_id=listing.ebay_item_id,
            title=listing.title,
            quantity=qty,
            listing_price=float(listing.listing_price) if listing.listing_price else None,
            status=status,
            variants=listing.variants,
        )

    def get_stock_summary(self) -> dict:
        """库存概览统计。"""
        from core.database.connection import get_session
        from core.models import EbayListing, ListingStatus

        with get_session() as sess:
            total = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ACTIVE
            ).count()
            oos = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ACTIVE,
                EbayListing.quantity_available == 0,
            ).count()
            low = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ACTIVE,
                EbayListing.quantity_available > 0,
                EbayListing.quantity_available <= DEFAULT_LOW_STOCK_THRESHOLD,
            ).count()
            ended = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ENDED
            ).count()
            return {
                "total_active": total,
                "out_of_stock": oos,
                "low_stock": low,
                "ended": ended,
            }
