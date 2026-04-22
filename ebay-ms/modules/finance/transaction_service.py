"""
modules/finance/transaction_service.py

Day 27: 独立的 Transaction 重建服务。

职责：
- 从已存在的 Order + OrderItem 数据，重建 SALE / FEE / SHIPPING Transaction 流水。
- REFUND / ADJUSTMENT 类型不受影响（不由本服务管理）。

与 OrderSyncService 的区别：
- OrderSyncService 从 eBay API 拉取数据写入 Order + Transaction。
- 本服务只读写 Transaction 表，基于已有 Order/OrderItem 数据做重建/修正。

每个 Order 的 Transaction 写入规则：
  SALE      : per SKU（每条 OrderItem 一条），amount = sale_amount × quantity
  FEE       : order-level，sku=NULL，amount = -ebay_fee（ebay_fee > 0 时才写）
  SHIPPING  : order-level，sku=NULL，amount = shipping_cost（shipping_cost > 0 时才写）
  REFUND    : 不动
  ADJUSTMENT: 不动
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from core.database.connection import get_session
from core.models import Order, OrderItem, Product, Transaction, TransactionType
from sqlalchemy import and_, delete
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    pass


# ── 结果 dataclass ────────────────────────────────────────────────────────


@dataclass
class RebuildResult:
    """rebuild_for_order / rebuild_all 的返回结果。"""
    order_id: str
    sale_count: int = 0      # 写入的 SALE 条数
    fee_count: int = 0       # 写入的 FEE 条数（0 或 1）
    shipping_count: int = 0  # 写入的 SHIPPING 条数（0 或 1）
    deleted_count: int = 0   # 本次覆盖删除的旧记录条数
    skipped_reason: str | None = None  # 跳过原因（如 "no_order_items"）

    def summary(self) -> str:
        if self.skipped_reason:
            return f"Order {self.order_id}: SKIP ({self.skipped_reason})"
        return (
            f"Order {self.order_id}: "
            f"SALE={self.sale_count} FEE={self.fee_count} "
            f"SHIPPING={self.shipping_count} deleted={self.deleted_count}"
        )


# ── 工具函数 ────────────────────────────────────────────────────────────────


def _decimal(val: Any) -> Decimal:
    """将 API/模型返回值转为 Decimal，失败返回 Decimal(0)。"""
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError):
        return Decimal("0")


# ── Service ────────────────────────────────────────────────────────────────


class TransactionService:
    """
    Transaction 读写服务（不依赖 eBay API）。

    用法::

        svc = TransactionService()
        result = svc.rebuild_for_order("ORD-123")
        print(result.summary())

        # 批量重建
        results = svc.rebuild_all(date_from=datetime(2026,1,1), date_to=datetime(2026,4,20))
    """

    def __init__(self, session: Session | None = None):
        self._external_session = session

    def _get_session(self) -> Session:
        if self._external_session is not None:
            return self._external_session
        return get_session()

    # ── 核心：重建 ────────────────────────────────────────────────────────

    def rebuild_for_order(
        self,
        order_id: str,
        *,
        overwrite: bool = True,
    ) -> RebuildResult:
        """
        对单个订单重建 SALE / FEE / SHIPPING Transaction。

        overwrite=True（默认）:
          - 先 DELETE 该 order_id 的所有 SALE / FEE / SHIPPING Transaction
          - 再从 Order + OrderItem 重新写入
          - REFUND / ADJUSTMENT 类型不受影响（不在删除范围内）

        overwrite=False:
          - 若该 order_id 已存在任何 SALE / FEE / SHIPPING Transaction → 跳过
          - 返回 skipped_reason="already_has_transactions"

        返回 RebuildResult。

        边界情况：
          - Order 不存在 → raise ValueError("order_not_found: {order_id}")
          - OrderItem 为空 → skipped_reason="no_order_items"（不写任何 Transaction，
            包括不写 FEE/SHIPPING，因为包着单没有可核算的 SKU）
          - Product 不存在或 cost_price 为 None → unit_cost=None / total_cost=None
            / profit=None / margin=None（不抛错）
          - ebay_fee == 0 → 不写 FEE 记录（fee_count=0）
          - shipping_cost == 0 → 不写 SHIPPING 记录（shipping_count=0）
        """
        sess = self._get_session()
        close_after = self._external_session is None

        try:
            # 1. 检查 Order 是否存在
            order: Order | None = sess.query(Order).filter(
                Order.ebay_order_id == order_id
            ).first()
            if not order:
                raise ValueError(f"order_not_found: {order_id}")

            # 2. 检查是否已有 Transaction（overwrite=False 时）
            if not overwrite:
                existing = sess.query(Transaction).filter(
                    Transaction.order_id == order_id,
                    Transaction.type.in_([
                        TransactionType.SALE,
                        TransactionType.FEE,
                        TransactionType.SHIPPING,
                    ]),
                ).first()
                if existing:
                    return RebuildResult(
                        order_id=order_id,
                        skipped_reason="already_has_transactions",
                    )

            # 3. 查 OrderItem
            items: list[OrderItem] = sess.query(OrderItem).filter(
                OrderItem.order_id == order_id
            ).all()
            if not items:
                return RebuildResult(
                    order_id=order_id,
                    skipped_reason="no_order_items",
                )

            # 4. 删除旧的 SALE / FEE / SHIPPING（overwrite=True 时）
            deleted_count = 0
            if overwrite:
                deleted = delete(Transaction).where(
                    and_(
                        Transaction.order_id == order_id,
                        Transaction.type.in_([
                            TransactionType.SALE,
                            TransactionType.FEE,
                            TransactionType.SHIPPING,
                        ]),
                    )
                )
                deleted_count = sess.execute(deleted).rowcount

            # 5. 写 SALE（per SKU）
            sale_count = 0
            order_date = order.order_date or datetime.now()
            for item in items:
                product: Product | None = sess.query(Product).filter(
                    Product.sku == item.sku
                ).first()
                unit_cost: Decimal | None = (
                    Decimal(str(product.cost_price))
                    if product and product.cost_price is not None
                    else None
                )
                sale_amount_dec = _decimal(item.sale_amount)
                qty = item.quantity or 1
                amount_val = sale_amount_dec * qty
                total_cost: Decimal | None = (
                    unit_cost * qty if unit_cost is not None else None
                )
                profit: Decimal | None = (
                    (amount_val - total_cost)  # type: ignore[arg-type]
                    if total_cost is not None
                    else None
                )
                margin: float | None = (
                    float(profit / sale_amount_dec)  # type: ignore[arg-type]
                    if profit is not None and sale_amount_dec != 0
                    else None
                )
                tx = Transaction(
                    order_id=order_id,
                    type=TransactionType.SALE,
                    amount=float(sale_amount_dec * qty),
                    currency="USD",
                    date=order_date,
                    sku=item.sku,
                    unit_cost=float(unit_cost) if unit_cost is not None else None,
                    total_cost=float(total_cost) if total_cost is not None else None,
                    profit=float(profit) if profit is not None else None,
                    margin=margin,
                )
                sess.add(tx)
                sale_count += 1

            # 6. 写 FEE（order-level，sku=NULL）
            fee_count = 0
            if order.ebay_fee:
                fee_amount = _decimal(order.ebay_fee)
                tx = Transaction(
                    order_id=order_id,
                    type=TransactionType.FEE,
                    amount=float(-fee_amount),
                    currency="USD",
                    date=order_date,
                    sku=None,
                    unit_cost=None,
                    total_cost=None,
                    profit=None,
                    margin=None,
                )
                sess.add(tx)
                fee_count = 1

            # 7. 写 SHIPPING（order-level，sku=NULL）
            shipping_count = 0
            if order.shipping_cost:
                tx = Transaction(
                    order_id=order_id,
                    type=TransactionType.SHIPPING,
                    amount=float(_decimal(order.shipping_cost)),
                    currency="USD",
                    date=order_date,
                    sku=None,
                    unit_cost=None,
                    total_cost=None,
                    profit=None,
                    margin=None,
                )
                sess.add(tx)
                shipping_count = 1

            if close_after:
                sess.commit()

            return RebuildResult(
                order_id=order_id,
                sale_count=sale_count,
                fee_count=fee_count,
                shipping_count=shipping_count,
                deleted_count=deleted_count,
            )

        except ValueError:
            # 不捕获，让异常上抛
            if close_after:
                sess.rollback()
            raise
        except Exception:
            if close_after:
                sess.rollback()
            raise

    def rebuild_all(
        self,
        *,
        overwrite: bool = True,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[RebuildResult]:
        """
        批量重建所有在指定日期范围内的 Order。

        date_from / date_to 按 Order.order_date 过滤。

        一个订单失败不影响其他订单 —— 失败的订单返回
        skipped_reason="error: {msg}"。
        """
        sess = self._get_session()
        close_after = self._external_session is None

        try:
            query = sess.query(Order.ebay_order_id)
            if date_from:
                query = query.filter(Order.order_date >= date_from)
            if date_to:
                query = query.filter(Order.order_date <= date_to)

            order_ids = [row[0] for row in query.all()]
        except Exception as exc:
            return [RebuildResult(
                order_id="<query_failed>",
                skipped_reason=f"error: {exc}",
            )]

        results: list[RebuildResult] = []
        for oid in order_ids:
            try:
                res = self.rebuild_for_order(oid, overwrite=overwrite)
                results.append(res)
            except ValueError as exc:
                results.append(RebuildResult(
                    order_id=oid,
                    skipped_reason=f"error: {exc}",
                ))
            except Exception as exc:
                results.append(RebuildResult(
                    order_id=oid,
                    skipped_reason=f"error: {exc}",
                ))

        if close_after:
            sess.commit()

        return results

    # ── 查询 ─────────────────────────────────────────────────────────────

    def list_by_order(self, order_id: str) -> list[Transaction]:
        """查询某订单的所有 Transaction（按 id 升序）。"""
        sess = self._get_session()
        return (
            sess.query(Transaction)
            .filter(Transaction.order_id == order_id)
            .order_by(Transaction.id)
            .all()
        )

    def list_by_type(
        self,
        tx_type: TransactionType,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[Transaction]:
        """按类型查询 Transaction（可选日期过滤）。"""
        sess = self._get_session()
        q = sess.query(Transaction).filter(Transaction.type == tx_type)
        if date_from:
            q = q.filter(Transaction.date >= date_from)
        if date_to:
            q = q.filter(Transaction.date <= date_to)
        return q.order_by(Transaction.date).all()

    def list_by_date_range(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> list[Transaction]:
        """查询指定日期范围内的所有 Transaction（不限类型）。"""
        sess = self._get_session()
        return (
            sess.query(Transaction)
            .filter(Transaction.date >= date_from, Transaction.date <= date_to)
            .order_by(Transaction.date)
            .all()
        )
