"""
modules/inventory_online/quantity_adjuster.py

Day 17: eBay 库存调整接口

功能：
- adjust_ebay_quantity(sku, new_quantity)：修改 eBay 上的库存数量
- 底层调用 eBay Inventory API 的 createOrReplaceInventoryItem
- 更新本地 EbayListing 表
- 发布 LISTING_UPDATED 事件
- 支持批量调整（从 CSV）
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from loguru import logger as log


@dataclass
class AdjustmentResult:
    """单次库存调整结果。"""
    sku: str
    old_quantity: int
    new_quantity: int
    success: bool
    error: str | None = None


@dataclass
class BatchAdjustmentResult:
    """批量调整结果。"""
    total: int
    success: int
    failed: int
    results: list[AdjustmentResult]


class QuantityAdjuster:
    """eBay 库存数量调整服务。"""

    def __init__(self, client=None):
        if client is None:
            from core.ebay_api.client import EbayClient
            client = EbayClient()
        self._client = client

    def adjust_ebay_quantity(
        self,
        sku: str,
        new_quantity: int,
        publish_event: bool = True,
    ) -> AdjustmentResult:
        """
        修改 eBay 上的库存数量，同时更新本地 EbayListing 表。

        Args:
            sku: 商品 SKU
            new_quantity: 新的库存数量
            publish_event: 是否发布 LISTING_UPDATED 事件

        Returns:
            AdjustmentResult

        Raises:
            ValueError: SKU 不存在或数量无效
            EbayApiError: API 调用失败
        """
        from core.database.connection import get_session
        from core.models import EbayListing

        if new_quantity < 0:
            raise ValueError(f"库存数量不能为负: {new_quantity}")

        with get_session() as sess:
            listing = sess.query(EbayListing).filter(EbayListing.sku == sku).first()
            if not listing:
                raise ValueError(f"SKU 不存在: {sku}")

            old_quantity = listing.quantity_available or 0
            if old_quantity == new_quantity:
                return AdjustmentResult(
                    sku=sku,
                    old_quantity=old_quantity,
                    new_quantity=new_quantity,
                    success=True,
                )

            # 调用 eBay Inventory API
            try:
                self._update_ebay_inventory(sku, new_quantity, listing.ebay_item_id)
            except Exception as e:
                logger = log.error
                logger(f"eBay API 更新 {sku} 库存失败: {e}")
                return AdjustmentResult(
                    sku=sku,
                    old_quantity=old_quantity,
                    new_quantity=new_quantity,
                    success=False,
                    error=str(e),
                )

            # 更新本地 DB
            listing.quantity_available = new_quantity
            sess.commit()

            if publish_event:
                self._publish_update_event(sku, old_quantity, new_quantity, listing.title)

            return AdjustmentResult(
                sku=sku,
                old_quantity=old_quantity,
                new_quantity=new_quantity,
                success=True,
            )

    def batch_adjust_from_csv(
        self,
        csv_path: str | Path,
        dry_run: bool = False,
    ) -> BatchAdjustmentResult:
        """
        从 CSV 批量调整库存。

        CSV 格式（header）：
            sku, new_quantity

        Args:
            csv_path: CSV 文件路径
            dry_run: True 则只打印不实际调整

        Returns:
            BatchAdjustmentResult
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

        results: list[AdjustmentResult] = []
        success = failed = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for row in rows:
            sku = (row.get("sku") or "").strip()
            qty_str = (row.get("new_quantity") or "").strip()

            if not sku:
                results.append(AdjustmentResult(sku="?", old_quantity=0, new_quantity=0,
                                               success=False, error="sku 为空"))
                failed += 1
                continue

            try:
                new_qty = int(qty_str)
            except (ValueError, TypeError):
                results.append(AdjustmentResult(sku=sku, old_quantity=0, new_quantity=0,
                                               success=False, error=f"无效数量: {qty_str}"))
                failed += 1
                continue

            if dry_run:
                results.append(AdjustmentResult(sku=sku, old_quantity=-1, new_quantity=new_qty,
                                               success=True))
                success += 1
                continue

            try:
                result = self.adjust_ebay_quantity(sku, new_qty)
                results.append(result)
                if result.success:
                    success += 1
                    log.info(f"✅ {sku}: {result.old_quantity} → {result.new_quantity}")
                else:
                    failed += 1
                    log.error(f"❌ {sku}: {result.error}")
            except Exception as e:
                results.append(AdjustmentResult(sku=sku, old_quantity=0, new_quantity=new_qty,
                                               success=False, error=str(e)))
                failed += 1
                log.error(f"❌ {sku}: {e}")

        return BatchAdjustmentResult(
            total=len(rows),
            success=success,
            failed=failed,
            results=results,
        )

    def _update_ebay_inventory(
        self,
        sku: str,
        quantity: int,
        ebay_item_id: str | None,
    ) -> None:
        """
        调用 eBay Inventory API 更新库存。

        eBay Inventory API: POST /inventory_item/{sku}
        Body: { "availability": { "shipToLocationAvailability": { "quantity": N } } }
        """
        from core.ebay_api.auth import EbayAuth

        auth = EbayAuth()
        token = auth.get_access_token()

        endpoint = f"{auth._get_api_url()}/inventory_item/{sku}"
        payload = {
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": quantity,
                }
            }
        }

        resp = self._client._session.put(  # type: ignore[attr-defined]
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        if not resp.is_success:
            from core.ebay_api.exceptions import EbayApiError
            raise EbayApiError(f"eBay API 返回 {resp.status_code}: {resp.text}")

    def _publish_update_event(
        self,
        sku: str,
        old_qty: int,
        new_qty: int,
        title: str | None,
    ) -> None:
        """发布 LISTING_UPDATED 事件。"""
        from core.events.bus import EventBus

        bus = EventBus()
        bus.publish(
            event_type="LISTING_UPDATED",
            payload={
                "sku": sku,
                "title": title,
                "field": "quantity",
                "old_value": old_qty,
                "new_value": new_qty,
                "message": f"{sku} 库存调整: {old_qty} → {new_qty}",
            },
        )
        log.info(f"LISTING_UPDATED: {sku} 库存 {old_qty} → {new_qty}")
