"""
modules/inventory_offline/stocktake_service.py

Day 21: 库存盘点服务

流程：
1. start_stocktake() — 创建盘点单，锁定系统库存快照
2. record_count() — 录入实际清点数量
3. finish_stocktake() — 计算差异，生成 ADJUST 记录
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger as log


@dataclass
class StocktakeResult:
    """盘点结果。"""
    stocktake_id: int
    status: str
    items_count: int
    total_difference: int
    adjustment_records: int


@dataclass
class AdjustmentDiff:
    """单个 SKU 的差异信息。"""
    sku: str
    system_quantity: int
    actual_quantity: int
    difference: int  # positive = more on shelf, negative = missing
    estimated_cost: Decimal | None = None


class StocktakeService:
    """库存盘点服务。"""

    def __init__(self):
        from core.database.connection import get_session
        from core.events.bus import EventBus
        from core.models import (
            Inventory,
            InventoryType,
            Product,
            Stocktake,
            StocktakeItem,
            StocktakeStatus,
        )
        from modules.inventory_offline.inbound_service import InboundService

        self._get_session = get_session
        self._Inventory = Inventory
        self._InventoryType = InventoryType
        self._Product = Product
        self._Stocktake = Stocktake
        self._StocktakeItem = StocktakeItem
        self._StocktakeStatus = StocktakeStatus
        self._InboundService = InboundService
        self._EventBus = EventBus

    def start_stocktake(
        self,
        skus: list[str] | None = None,
        operator: str | None = None,
        note: str | None = None,
    ) -> dict:
        """
        创建盘点单，并锁定所有指定 SKU 的当前系统库存。

        Args:
            skus: 要盘点的 SKU 列表（None = 所有活跃商品）
            operator: 操作人
            note: 备注

        Returns:
            dict，含 stocktake_id, items_count, started_at
        """
        with self._get_session() as sess:
            now = datetime.now(timezone.utc)

            # 创建盘点单
            stocktake = self._Stocktake(
                status=self._StocktakeStatus.IN_PROGRESS,
                started_at=now,
                operator=operator,
                note=note,
            )
            sess.add(stocktake)
            sess.flush()

            # 确定要盘点的 SKU
            if skus:
                products = sess.query(self._Product).filter(
                    self._Product.sku.in_(skus),
                    self._Product.status != "discontinued",
                ).all()
            else:
                products = sess.query(self._Product).filter(
                    self._Product.status != "discontinued",
                ).all()

            # 查询每个 SKU 的系统可用库存，写入盘点明细
            offline_svc = self._InboundService()
            items_created = 0
            for prod in products:
                # 获取当前系统可用库存
                stock = offline_svc.get_stock(prod.sku)
                system_qty = stock.get("available_quantity", 0)

                item = self._StocktakeItem(
                    stocktake_id=stocktake.id,
                    sku=prod.sku,
                    system_quantity=system_qty,
                    actual_quantity=None,
                    difference=None,
                )
                sess.add(item)
                items_created += 1

            sess.commit()
            log.info(f"创建盘点单 #{stocktake.id}，{items_created} 个 SKU")

            return {
                "stocktake_id": stocktake.id,
                "items_count": items_created,
                "started_at": now.isoformat(),
            }

    def record_count(
        self,
        stocktake_id: int,
        counts: dict[str, int],
    ) -> dict:
        """
        录入实际清点数量。

        Args:
            stocktake_id: 盘点单 ID
            counts: dict[sku, actual_quantity]

        Returns:
            dict，含 items_updated, differences（有差异的 SKU 列表）
        """
        with self._get_session() as sess:
            stocktake = sess.query(self._Stocktake).filter(
                self._Stocktake.id == stocktake_id
            ).first()
            if not stocktake:
                raise ValueError(f"盘点单不存在: {stocktake_id}")
            if stocktake.status.value == "finished":
                raise ValueError(f"盘点单 #{stocktake_id} 已结束，无法录入")
            if stocktake.status.value == "cancelled":
                raise ValueError(f"盘点单 #{stocktake_id} 已取消")

            items = sess.query(self._StocktakeItem).filter(
                self._StocktakeItem.stocktake_id == stocktake_id
            ).all()

            sku_to_item = {it.sku: it for it in items}
            missing_skus = set(counts.keys()) - set(sku_to_item.keys())
            if missing_skus:
                raise ValueError(f"以下 SKU 不在盘点单中: {missing_skus}")

            items_updated = 0
            differences: list[AdjustmentDiff] = []

            for sku, actual_qty in counts.items():
                item = sku_to_item[sku]
                item.actual_quantity = actual_qty
                item.difference = actual_qty - item.system_quantity
                items_updated += 1

                if item.difference != 0:
                    # 查找 cost_price 用于差异金额估算
                    prod = sess.query(self._Product).filter(
                        self._Product.sku == sku
                    ).first()
                    cost = Decimal(str(prod.cost_price)) if prod else None
                    differences.append(AdjustmentDiff(
                        sku=sku,
                        system_quantity=item.system_quantity,
                        actual_quantity=actual_qty,
                        difference=item.difference,
                        estimated_cost=cost,
                    ))

            sess.commit()
            log.info(f"盘点单 #{stocktake_id} 录入 {items_updated} 项，{len(differences)} 项有差异")

            return {
                "stocktake_id": stocktake_id,
                "items_updated": items_updated,
                "differences": [
                    {
                        "sku": d.sku,
                        "system": d.system_quantity,
                        "actual": d.actual_quantity,
                        "diff": d.difference,
                        "est_cost": str(d.estimated_cost) if d.estimated_cost else None,
                    }
                    for d in differences
                ],
            }

    def finish_stocktake(self, stocktake_id: int) -> StocktakeResult:
        """
        结束盘点：计算差异，生成 Inventory(type=ADJUST) 记录。

        仅对 actual_quantity 已有值的 SKU 生成调整记录。
        差异 = actual - system，正数表示盘盈，负数表示盘亏。

        Args:
            stocktake_id: 盘点单 ID

        Returns:
            StocktakeResult
        """
        with self._get_session() as sess:
            stocktake = sess.query(self._Stocktake).filter(
                self._Stocktake.id == stocktake_id
            ).first()
            if not stocktake:
                raise ValueError(f"盘点单不存在: {stocktake_id}")
            if stocktake.status.value == "finished":
                raise ValueError(f"盘点单 #{stocktake_id} 已结束")
            if stocktake.status.value == "cancelled":
                raise ValueError(f"盘点单 #{stocktake_id} 已取消")

            items = sess.query(self._StocktakeItem).filter(
                self._StocktakeItem.stocktake_id == stocktake_id,
                self._StocktakeItem.actual_quantity.isnot(None),
            ).all()

            now = datetime.now(timezone.utc)
            adjustment_records = 0
            total_difference = 0

            for item in items:
                if item.difference == 0:
                    continue

                # 生成 ADJUST 记录
                adj = self._Inventory(
                    sku=item.sku,
                    type=self._InventoryType.ADJUST,
                    quantity=item.difference,
                    related_order=f"STOCKTAKE-{stocktake_id}",
                    operator=stocktake.operator,
                    note=f"盘点调整（盘点单 #{stocktake_id}）",
                    occurred_at=now,
                )
                sess.add(adj)
                adjustment_records += 1
                total_difference += item.difference

            stocktake.status = self._StocktakeStatus.FINISHED
            stocktake.finished_at = now
            sess.commit()

            # 发布事件
            bus = self._EventBus()
            bus.publish(
                event_type="STOCKTAKE_FINISHED",
                payload={
                    "stocktake_id": stocktake_id,
                    "items_count": len(items),
                    "adjustment_records": adjustment_records,
                    "total_difference": total_difference,
                    "operator": stocktake.operator,
                },
            )

            log.info(
                f"盘点单 #{stocktake_id} 结束："
                f"{len(items)} 项已清点，"
                f"{adjustment_records} 条调整记录，"
                f"总差异: {total_difference:+d}"
            )

            return StocktakeResult(
                stocktake_id=stocktake_id,
                status="finished",
                items_count=len(items),
                total_difference=total_difference,
                adjustment_records=adjustment_records,
            )

    def cancel_stocktake(self, stocktake_id: int) -> dict:
        """取消盘点单（仅 IN_PROGRESS 可取消）。"""
        with self._get_session() as sess:
            stocktake = sess.query(self._Stocktake).filter(
                self._Stocktake.id == stocktake_id
            ).first()
            if not stocktake:
                raise ValueError(f"盘点单不存在: {stocktake_id}")
            if stocktake.status.value != "in_progress":
                raise ValueError(f"盘点单状态为 {stocktake.status.value}，无法取消")

            stocktake.status = self._StocktakeStatus.CANCELLED
            sess.commit()
            log.info(f"取消盘点单 #{stocktake_id}")
            return {"stocktake_id": stocktake_id, "status": "cancelled"}

    def get_stocktake(self, stocktake_id: int) -> dict:
        """获取盘点单完整信息（含明细）。"""
        with self._get_session() as sess:
            stocktake = sess.query(self._Stocktake).filter(
                self._Stocktake.id == stocktake_id
            ).first()
            if not stocktake:
                raise ValueError(f"盘点单不存在: {stocktake_id}")

            items = sess.query(self._StocktakeItem).filter(
                self._StocktakeItem.stocktake_id == stocktake_id
            ).all()

            total_diff = sum(it.difference or 0 for it in items)
            unrecorded = sum(1 for it in items if it.actual_quantity is None)

            return {
                "id": stocktake.id,
                "status": stocktake.status.value,
                "started_at": stocktake.started_at,
                "finished_at": stocktake.finished_at,
                "operator": stocktake.operator,
                "note": stocktake.note,
                "items": [
                    {
                        "sku": it.sku,
                        "system_quantity": it.system_quantity,
                        "actual_quantity": it.actual_quantity,
                        "difference": it.difference,
                        "note": it.note,
                    }
                    for it in items
                ],
                "summary": {
                    "total_items": len(items),
                    "unrecorded": unrecorded,
                    "with_difference": sum(1 for it in items if it.difference and it.difference != 0),
                    "total_difference": total_diff,
                },
            }

    def list_stocktakes(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出典型盘点单。"""
        with self._get_session() as sess:
            q = sess.query(self._Stocktake)
            if status:
                q = q.filter(self._Stocktake.status == status)
            rows = q.order_by(self._Stocktake.started_at.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "status": r.status.value,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                    "operator": r.operator,
                }
                for r in rows
            ]
