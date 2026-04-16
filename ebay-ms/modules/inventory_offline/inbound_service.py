"""
modules/inventory_offline/inbound_service.py

Day 19: 入库功能服务

流程：
1. create_receipt() — 创建入库单（待发货）
2. confirm_inbound() — 到货确认，生成 Inventory.IN 变动记录
3. cancel_receipt() — 取消入库单

支持：部分收货 / 超量收货 / 拒收
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger as log


@dataclass
class InboundItemInput:
    """入库单项输入。"""
    sku: str
    expected_quantity: int
    cost_price: Decimal | float
    note: str | None = None


@dataclass
class ReceivedItemInput:
    """到货确认输入。"""
    sku: str
    received_quantity: int
    note: str | None = None


@dataclass
class InboundReceiptResult:
    """创建入库单结果。"""
    receipt_id: int
    receipt_no: str
    status: str
    item_count: int


@dataclass
class ConfirmResult:
    """到货确认结果。"""
    receipt_id: int
    receipt_no: str
    status: str
    items_confirmed: int
    total_received: int
    inventory_records: int


class InboundService:
    """入库单服务。"""

    def __init__(self):
        from core.database.connection import get_session
        from core.events.bus import EventBus
        from core.models import (
            InboundReceipt,
            InboundReceiptItem,
            InboundStatus,
            Inventory,
            InventoryType,
            Product,
        )

        self._get_session = get_session
        self._InboundReceipt = InboundReceipt
        self._InboundReceiptItem = InboundReceiptItem
        self._InboundStatus = InboundStatus
        self._Inventory = Inventory
        self._InventoryType = InventoryType
        self._Product = Product
        self._EventBus = EventBus

    # ── 入库单管理 ──────────────────────────────────────

    def create_receipt(
        self,
        supplier: str,
        items: list[InboundItemInput],
        receipt_no: str | None = None,
        expected_date: datetime | None = None,
        operator: str | None = None,
        note: str | None = None,
    ) -> InboundReceiptResult:
        """
        创建入库单（状态=PENDING，待发货）。

        Args:
            supplier: 供应商名称
            items: 入库物品列表
            receipt_no: 入库单号，默认自动生成
            expected_date: 预计到货时间
            operator: 操作人
            note: 备注

        Returns:
            InboundReceiptResult

        Raises:
            ValueError: 物品列表为空或 SKU 不存在
        """
        if not items:
            raise ValueError("物品列表不能为空")

        if receipt_no is None:
            receipt_no = self._generate_receipt_no()

        with self._get_session() as sess:
            # 校验 SKU 都存在
            skus = [item.sku for item in items]
            existing = sess.query(self._Product.sku).filter(
                self._Product.sku.in_(skus)
            ).all()
            existing_skus = {row[0] for row in existing}
            missing = set(skus) - existing_skus
            if missing:
                raise ValueError(f"SKU 不存在: {missing}")

            # 创建入库单
            receipt = self._InboundReceipt(
                receipt_no=receipt_no,
                supplier=supplier,
                status=self._InboundStatus.PENDING,
                expected_date=expected_date,
                operator=operator,
                note=note,
            )
            sess.add(receipt)
            sess.flush()  # 获取 receipt.id

            # 创建物品行
            for item in items:
                row = self._InboundReceiptItem(
                    receipt_id=receipt.id,
                    sku=item.sku,
                    expected_quantity=item.expected_quantity,
                    received_quantity=0,
                    cost_price=Decimal(str(item.cost_price)),
                    note=item.note,
                )
                sess.add(row)

            sess.commit()
            log.info(f"创建入库单 {receipt_no}，{len(items)} 个 SKU")

            return InboundReceiptResult(
                receipt_id=receipt.id,
                receipt_no=receipt_no,
                status="pending",
                item_count=len(items),
            )

    def confirm_inbound(
        self,
        receipt_id: int,
        received_items: list[ReceivedItemInput],
        operator: str | None = None,
        location: str | None = None,
    ) -> ConfirmResult:
        """
        到货确认。

        将收货数量更新到 InboundReceiptItem，
        同时为每个 SKU 生成一条 Inventory(type=IN) 变动记录。

        支持部分收货（状态变为 PARTIAL）和超量收货
        （received > expected 时仍计入，但记录 note）。

        Args:
            receipt_id: 入库单 ID
            received_items: 实际收货明细
            operator: 操作人
            location: 存放库位

        Returns:
            ConfirmResult

        Raises:
            ValueError: 入库单不存在或已全部收货
        """
        with self._get_session() as sess:
            receipt = sess.query(self._InboundReceipt).filter(
                self._InboundReceipt.id == receipt_id
            ).first()
            if not receipt:
                raise ValueError(f"入库单不存在: {receipt_id}")

            if receipt.status.value == "received":
                raise ValueError(f"入库单 {receipt.receipt_no} 已全部收货，无法重复确认")
            if receipt.status.value == "cancelled":
                raise ValueError(f"入库单 {receipt.receipt_no} 已取消")

            # 索引：sku -> received_quantity
            received_map = {item.sku: item for item in received_items}

            # 查询所有物品行
            item_rows = sess.query(self._InboundReceiptItem).filter(
                self._InboundReceiptItem.receipt_id == receipt_id
            ).all()

            total_received = 0
            inventory_records = 0
            now = datetime.now(timezone.utc)

            for row in item_rows:
                rec = received_map.get(row.sku)
                if rec is None:
                    # 未收到，skip
                    continue

                # 更新收货数量
                row.received_quantity = rec.received_quantity
                if rec.note:
                    row.note = (row.note or "") + f" | {rec.note}"

                # 生成 Inventory 变动记录（入库数量 = 实际收货数量）
                inv = self._Inventory(
                    sku=row.sku,
                    type=self._InventoryType.IN,
                    quantity=rec.received_quantity,
                    related_order=receipt.receipt_no,
                    location=location,
                    operator=operator,
                    occurred_at=now,
                )
                sess.add(inv)
                inventory_records += 1
                total_received += rec.received_quantity

                # 更新 Product 表的 cost_price（以最新收货价为准）
                prod = sess.query(self._Product).filter(
                    self._Product.sku == row.sku
                ).first()
                if prod:
                    prod.cost_price = row.cost_price

            # 更新入库单状态
            all_received = all(
                row.received_quantity >= row.expected_quantity for row in item_rows
            )
            any_received = any(row.received_quantity > 0 for row in item_rows)

            if all_received:
                receipt.status = self._InboundStatus.RECEIVED
                receipt.received_date = now
            elif any_received:
                receipt.status = self._InboundStatus.PARTIAL
            # PENDING / SHIPPED 状态不变

            sess.commit()

            # 发布事件
            bus = self._EventBus()
            bus.publish(
                event_type="INBOUND_CONFIRMED",
                payload={
                    "receipt_id": receipt_id,
                    "receipt_no": receipt.receipt_no,
                    "supplier": receipt.supplier,
                    "items_confirmed": len(received_items),
                    "total_received": total_received,
                    "inventory_records": inventory_records,
                    "operator": operator,
                },
            )

            log.info(
                f"入库确认 {receipt.receipt_no}："
                f"{len(received_items)} 项确认，"
                f"{total_received} 件入库，"
                f"状态 → {receipt.status.value}"
            )

            return ConfirmResult(
                receipt_id=receipt_id,
                receipt_no=receipt.receipt_no,
                status=receipt.status.value,
                items_confirmed=len(received_items),
                total_received=total_received,
                inventory_records=inventory_records,
            )

    def get_receipt(self, receipt_id: int) -> dict:
        """获取入库单完整信息（含物品明细）。"""
        with self._get_session() as sess:
            receipt = sess.query(self._InboundReceipt).filter(
                self._InboundReceipt.id == receipt_id
            ).first()
            if not receipt:
                raise ValueError(f"入库单不存在: {receipt_id}")

            items = sess.query(self._InboundReceiptItem).filter(
                self._InboundReceiptItem.receipt_id == receipt_id
            ).all()

            return {
                "id": receipt.id,
                "receipt_no": receipt.receipt_no,
                "supplier": receipt.supplier,
                "status": receipt.status.value,
                "expected_date": receipt.expected_date,
                "received_date": receipt.received_date,
                "note": receipt.note,
                "operator": receipt.operator,
                "items": [
                    {
                        "sku": it.sku,
                        "expected_quantity": it.expected_quantity,
                        "received_quantity": it.received_quantity,
                        "cost_price": str(it.cost_price),
                        "note": it.note,
                    }
                    for it in items
                ],
            }

    def list_receipts(
        self,
        status: str | None = None,
        supplier: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出入库单（支持按状态 / 供应商筛选）。"""
        with self._get_session() as sess:
            q = sess.query(self._InboundReceipt)
            if status:
                q = q.filter(self._InboundReceipt.status == status)
            if supplier:
                q = q.filter(self._InboundReceipt.supplier == supplier)
            receipts = q.order_by(self._InboundReceipt.created_at.desc()).limit(limit).all()

            return [
                {
                    "id": r.id,
                    "receipt_no": r.receipt_no,
                    "supplier": r.supplier,
                    "status": r.status.value,
                    "expected_date": r.expected_date,
                    "received_date": r.received_date,
                    "operator": r.operator,
                }
                for r in receipts
            ]

    def cancel_receipt(self, receipt_id: int) -> dict:
        """取消入库单（仅 PENDING/SHIPPED 可取消）。"""
        with self._get_session() as sess:
            receipt = sess.query(self._InboundReceipt).filter(
                self._InboundReceipt.id == receipt_id
            ).first()
            if not receipt:
                raise ValueError(f"入库单不存在: {receipt_id}")
            if receipt.status.value in ("received", "cancelled"):
                raise ValueError(f"入库单 {receipt.receipt_no} 状态为 {receipt.status.value}，无法取消")

            receipt.status = self._InboundStatus.CANCELLED
            sess.commit()

            log.info(f"取消入库单 {receipt.receipt_no}")
            return {"receipt_no": receipt.receipt_no, "status": "cancelled"}

    def get_stock(self, sku: str) -> dict:
        """
        查询指定 SKU 的当前库存。

        Returns:
            dict，含 keys: sku, available_quantity, location_breakdown, last_movement_at
        """
        from sqlalchemy import func

        with self._get_session() as sess:
            # 汇总各类 Inventory 变动
            result = sess.query(
                self._Inventory.type,
                func.sum(self._Inventory.quantity).label("total"),
            ).filter(
                self._Inventory.sku == sku
            ).group_by(
                self._Inventory.type
            ).all()

            totals: dict[str, int] = {}
            for inv_type, total in result:
                totals[inv_type.value] = int(total or 0)

            inbound = totals.get("in", 0)
            outbound = totals.get("out", 0)
            adjust = totals.get("adjust", 0)
            ret = totals.get("return", 0)
            available = inbound - outbound + adjust + ret

            # 按库位分布
            loc_rows = sess.query(
                self._Inventory.location,
                func.sum(self._Inventory.quantity).label("qty"),
            ).filter(
                self._Inventory.sku == sku,
                self._Inventory.location.isnot(None),
            ).group_by(
                self._Inventory.location
            ).all()

            # 最近变动时间
            last_row = sess.query(
                self._Inventory.occurred_at
            ).filter(
                self._Inventory.sku == sku
            ).order_by(
                self._Inventory.occurred_at.desc()
            ).first()

            return {
                "sku": sku,
                "available_quantity": available,
                "total_in": inbound,
                "total_out": outbound,
                "total_adjust": adjust,
                "total_return": ret,
                "location_breakdown": {
                    row.location: int(row.qty) for row in loc_rows if row.qty
                },
                "last_movement_at": last_row.occurred_at if last_row else None,
            }

    def get_all_stock(self, limit: int = 200) -> list[dict]:
        """
        返回所有 SKU 的当前库存快照（按 available_quantity 倒序）。

        Args:
            limit: 最多返回 SKU 数，默认 200
        """
        from sqlalchemy import case, func

        with self._get_session() as sess:
            # 子查询：每个 SKU 的各类汇总
            subq = sess.query(
                self._Inventory.sku,
                func.sum(
                    case(
                        (self._Inventory.type == self._InventoryType.IN, self._Inventory.quantity),
                        (self._Inventory.type == self._InventoryType.RETURN, self._Inventory.quantity),
                        else_=0,
                    )
                ).label("total_in"),
                func.sum(
                    case(
                        (self._Inventory.type == self._InventoryType.OUT, self._Inventory.quantity),
                        else_=0,
                    )
                ).label("total_out"),
                func.sum(
                    case(
                        (self._Inventory.type == self._InventoryType.ADJUST, self._Inventory.quantity),
                        else_=0,
                    )
                ).label("total_adjust"),
            ).group_by(
                self._Inventory.sku
            ).subquery()

            rows = sess.query(
                self._Product.sku,
                self._Product.title,
                subq.c.total_in,
                subq.c.total_out,
                subq.c.total_adjust,
            ).outerjoin(
                subq, self._Product.sku == subq.c.sku
            ).filter(
                self._Product.status != "discontinued"
            ).limit(limit).all()

            rows = sess.query(
                self._Product.sku,
                self._Product.title,
                self._Product.cost_price,
                subq.c.total_in,
                subq.c.total_out,
                subq.c.total_adjust,
            ).outerjoin(
                subq, self._Product.sku == subq.c.sku
            ).filter(
                self._Product.status != "discontinued"
            ).limit(limit).all()

            result = []
            for r in rows:
                sku = r.sku

                # 位置分布 — 按 type 区分符号（仅 OUT 取负；ADJUST/RETURN/IN 按原符号）
                from sqlalchemy import case
                qty_expr = case(
                    (self._Inventory.type == self._InventoryType.OUT, -self._Inventory.quantity),
                    else_=self._Inventory.quantity,
                )
                loc_rows = sess.query(
                    self._Inventory.location,
                    func.sum(qty_expr).label("qty"),
                ).filter(
                    self._Inventory.sku == sku,
                    self._Inventory.location.isnot(None),
                ).group_by(
                    self._Inventory.location
                ).all()
                locations = {loc: int(qty) for loc, qty in loc_rows if qty and qty > 0}

                # 最后入库 / 出库时间
                last_in = sess.query(
                    func.max(self._Inventory.occurred_at)
                ).filter(
                    self._Inventory.sku == sku,
                    self._Inventory.type == self._InventoryType.IN,
                ).scalar()
                last_out = sess.query(
                    func.max(self._Inventory.occurred_at)
                ).filter(
                    self._Inventory.sku == sku,
                    self._Inventory.type == self._InventoryType.OUT,
                ).scalar()

                result.append({
                    "sku": sku,
                    "title": r.title,
                    "cost_price": r.cost_price,
                    "available_quantity": max(
                        int((r.total_in or 0) - (r.total_out or 0) + (r.total_adjust or 0)),
                        0,
                    ),
                    "total_in": int(r.total_in or 0),
                    "total_out": int(r.total_out or 0),
                    "total_adjust": int(r.total_adjust or 0),
                    "locations": locations,
                    "last_inbound_at": last_in,
                    "last_outbound_at": last_out,
                })

            # 按库存金额降序（cost_price * available_quantity）
            result.sort(
                key=lambda x: float(x["cost_price"] or 0) * x["available_quantity"],
                reverse=True,
            )
            return result[:limit]




    def outbound(
        self,
        sku: str,
        quantity: int,
        related_order: str | None = None,
        operator: str | None = None,
        location: str | None = None,
        note: str | None = None,
    ) -> dict:
        """
        出库：创建 Inventory(type=OUT) 变动记录。

        校验库存是否充足（available_quantity >= quantity）。
        成功后发布 STOCK_OUT 事件。

        Args:
            sku: 商品 SKU
            quantity: 出库数量（正数）
            related_order: 关联订单号
            operator: 操作人
            location: 出库库位
            note: 备注

        Returns:
            dict，含 outbound record 信息

        Raises:
            ValueError: 库存不足或 SKU 不存在
        """
        if quantity <= 0:
            raise ValueError(f"出库数量必须 > 0，实际: {quantity}")

        with self._get_session() as sess:
            # 检查库存是否充足
            stock = self._compute_available(sess, sku)
            if stock < quantity:
                raise ValueError(
                    f"库存不足：{sku} 当前可用 {stock} 件，申请出库 {quantity} 件"
                )

            # 记录出库
            now = datetime.now(timezone.utc)
            inv = self._Inventory(
                sku=sku,
                type=self._InventoryType.OUT,
                quantity=quantity,
                related_order=related_order,
                location=location,
                operator=operator,
                note=note,
                occurred_at=now,
            )
            sess.add(inv)
            sess.commit()

            # 查询 cost_price（用于财务记账）
            prod = sess.query(self._Product).filter(
                self._Product.sku == sku
            ).first()
            cost_price = str(prod.cost_price) if prod else None

            # 发布 STOCK_OUT 事件
            bus = self._EventBus()
            bus.publish(
                event_type="STOCK_OUT",
                payload={
                    "sku": sku,
                    "quantity": quantity,
                    "related_order": related_order,
                    "cost_price": cost_price,
                    "operator": operator,
                    "occurred_at": now.isoformat(),
                },
            )

            log.info(f"出库 {sku} × {quantity}，关联订单: {related_order or '—'}")

            return {
                "sku": sku,
                "quantity": quantity,
                "related_order": related_order,
                "remaining_stock": stock - quantity,
            }

    def return_inventory(
        self,
        sku: str,
        quantity: int,
        related_order: str | None = None,
        operator: str | None = None,
        note: str | None = None,
    ) -> dict:
        """
        退货：创建 Inventory(type=RETURN) 变动记录（增加库存）。

        Args:
            sku: 商品 SKU
            quantity: 退货数量（正数）
            related_order: 关联订单号
            operator: 操作人
            note: 备注

        Returns:
            dict
        """
        if quantity <= 0:
            raise ValueError(f"退货数量必须 > 0，实际: {quantity}")

        with self._get_session() as sess:
            now = datetime.now(timezone.utc)
            inv = self._Inventory(
                sku=sku,
                type=self._InventoryType.RETURN,
                quantity=quantity,
                related_order=related_order,
                operator=operator,
                note=note,
                occurred_at=now,
            )
            sess.add(inv)
            sess.commit()

            bus = self._EventBus()
            bus.publish(
                event_type="STOCK_RETURN",
                payload={
                    "sku": sku,
                    "quantity": quantity,
                    "related_order": related_order,
                    "operator": operator,
                },
            )

            log.info(f"退货入库 {sku} × {quantity}")

            return {"sku": sku, "quantity": quantity, "related_order": related_order}

    def list_outbound(
        self,
        sku: str | None = None,
        related_order: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        查询出库记录。

        Args:
            sku: 按 SKU 筛选
            related_order: 按订单号筛选
            start_date: 按开始日期筛选
            end_date: 按结束日期筛选
            limit: 返回条数上限
        """
        with self._get_session() as sess:
            q = sess.query(self._Inventory).filter(
                self._Inventory.type == self._InventoryType.OUT
            )
            if sku:
                q = q.filter(self._Inventory.sku == sku)
            if related_order:
                q = q.filter(self._Inventory.related_order == related_order)
            if start_date:
                q = q.filter(self._Inventory.occurred_at >= start_date)
            if end_date:
                q = q.filter(self._Inventory.occurred_at <= end_date)

            rows = q.order_by(self._Inventory.occurred_at.desc()).limit(limit).all()

            return [
                {
                    "sku": r.sku,
                    "quantity": r.quantity,
                    "related_order": r.related_order,
                    "location": r.location,
                    "operator": r.operator,
                    "note": r.note,
                    "occurred_at": r.occurred_at,
                }
                for r in rows
            ]

    # ── 内部方法 ──────────────────────────────────────

    def _compute_available(self, sess, sku: str) -> int:
        """计算指定 SKU 的可用库存（in - out + adjust + return）。"""
        from sqlalchemy import case, func

        result = sess.query(
            func.sum(
                case(
                    (
                        self._Inventory.type.in_(
                            [self._InventoryType.IN, self._InventoryType.RETURN]
                        ),
                        self._Inventory.quantity,
                    ),
                    else_=0,
                )
            ).label("in_total"),
            func.sum(
                case(
                    (self._Inventory.type == self._InventoryType.OUT, self._Inventory.quantity),
                    else_=0,
                )
            ).label("out_total"),
            func.sum(
                case(
                    (self._Inventory.type == self._InventoryType.ADJUST, self._Inventory.quantity),
                    else_=0,
                )
            ).label("adj_total"),
        ).filter(self._Inventory.sku == sku).first()

        inbound = int(result.in_total or 0)
        outbound = int(result.out_total or 0)
        adjust = int(result.adj_total or 0)
        return inbound - outbound + adjust

    def _generate_receipt_no(self) -> str:
        """生成入库单号：IN-YYYY-MM-DD-NNN"""
        import random
        today = datetime.today().date().isoformat()
        seq = random.randint(1, 999)
        return f"IN-{today}-{seq:03d}"
