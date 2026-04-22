"""
modules/finance/transaction_service.py

Day 27 — TransactionService
Rebuild: reproduce Transaction rows equivalent to what OrderSyncService wrote.

Contract rules (from OrderSyncService):
  SALE:   amount = float(item.sale_amount)   [item.sale_amount already = unit_price * qty]
          total_cost = unit_cost * qty
          profit = amount - total_cost
          margin = profit / amount
  FEE:    amount = -float(Order.ebay_fee)
  SHIPPING: amount = float(Order.shipping_cost)

Rebuild definition: re-produce Transaction rows that are byte-equivalent to
what OrderSyncService wrote. OrderSyncService is the source of truth.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.models import Order, OrderItem, Product, Transaction, TransactionType
from core.utils.currency import RateNotFoundError, convert
from modules.finance.order_sync_service import _decimal
from sqlalchemy.orm import Session


@dataclass
class RebuildResult:
    order_id: str
    sale_count: int
    fee_count: int
    shipping_count: int
    deleted_count: int
    skipped_reason: str | None = None


class TransactionService:
    def __init__(self, session: Session | None = None):
        self._session = session

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        from core.database.connection import get_session
        return get_session()

    def rebuild_for_order(self, order_id: str, *, overwrite: bool = True) -> RebuildResult:
        """
        Rebuild SALE / FEE / SHIPPING transactions for one order.

        overwrite=True (default):
          DELETE existing SALE/FEE/SHIPPING for this order_id first,
          then rewrite from Order + OrderItem.
          REFUND/ADJUSTMENT rows are NOT touched (out of scope for this service).

        overwrite=False:
          If any SALE/FEE/SHIPPING already exists for this order_id,
          skip and return skipped_reason="already_has_transactions".

        Edge cases:
          - Order not found → ValueError("order_not_found: {order_id}")
          - Order has no OrderItems → skipped_reason="no_order_items", no rows written
          - Product.cost_price missing → unit_cost=None / total_cost=None / profit=None / margin=None
          - Order.ebay_fee == 0 → no FEE row written (fee_count=0)
          - Order.shipping_cost == 0 → no SHIPPING row written (shipping_count=0)
        """
        sess = self._get_session()
        owns_session = self._session is None
        try:
            order = sess.query(Order).filter(Order.ebay_order_id == order_id).first()
            if not order:
                raise ValueError(f"order_not_found: {order_id}")

            items = (
                sess.query(OrderItem)
                .filter(OrderItem.order_id == order_id)
                .all()
            )
            if not items:
                return RebuildResult(
                    order_id=order_id,
                    sale_count=0, fee_count=0, shipping_count=0,
                    deleted_count=0,
                    skipped_reason="no_order_items",
                )

            existing = (
                sess.query(Transaction)
                .filter(
                    Transaction.order_id == order_id,
                    Transaction.type.in_(
                        [TransactionType.SALE, TransactionType.FEE, TransactionType.SHIPPING]
                    ),
                )
                .all()
            )
            if existing and not overwrite:
                return RebuildResult(
                    order_id=order_id,
                    sale_count=0, fee_count=0, shipping_count=0,
                    deleted_count=0,
                    skipped_reason="already_has_transactions",
                )

            deleted_count = len(existing)
            if deleted_count > 0:
                for tx in existing:
                    sess.delete(tx)

            order_date: datetime | None = order.order_date
            sale_count = 0
            for item in items:
                amount_val: float = float(item.sale_amount)
                qty = item.quantity or 1
                product: Product | None = sess.query(Product).filter(Product.sku == item.sku).first()
                unit_cost_val: float | None = (
                    float(product.cost_price) if product and product.cost_price is not None else None
                )
                amount_jpy_val: float | None = None
                exchange_rate_val: float | None = None
                if order_date is not None:
                    try:
                        amount_jpy, rate_used, _actual = convert(
                            sess,
                            Decimal(str(amount_val)),
                            "USD",
                            "JPY",
                            order_date.date(),
                        )
                        amount_jpy_val = float(amount_jpy)
                        exchange_rate_val = float(rate_used)
                    except RateNotFoundError:
                        pass
                total_cost_val: float | None = (
                    float(unit_cost_val * qty) if unit_cost_val is not None else None
                )
                profit_val: float | None = (
                    amount_jpy_val - total_cost_val
                    if amount_jpy_val is not None and total_cost_val is not None
                    else None
                )
                margin_val: float | None = (
                    profit_val / amount_jpy_val
                    if profit_val is not None and amount_jpy_val not in (None, 0)
                    else None
                )
                sess.add(Transaction(
                    order_id=order_id,
                    type=TransactionType.SALE,
                    amount=amount_val,
                    currency="USD",
                    amount_jpy=amount_jpy_val,
                    exchange_rate=exchange_rate_val,
                    date=order_date,
                    sku=item.sku,
                    unit_cost=unit_cost_val,
                    total_cost=total_cost_val,
                    profit=profit_val,
                    margin=margin_val,
                ))
                sale_count += 1

            fee_count = 0
            if order.ebay_fee:
                fee_dec = _decimal(order.ebay_fee)
                if fee_dec > 0:
                    fee_amount_jpy: float | None = None
                    fee_exchange_rate: float | None = None
                    if order_date is not None:
                        try:
                            converted, rate_used, _actual = convert(
                                sess, Decimal(str(-fee_dec)), "USD", "JPY", order_date.date()
                            )
                            fee_amount_jpy = float(converted)
                            fee_exchange_rate = float(rate_used)
                        except RateNotFoundError:
                            pass
                    sess.add(Transaction(
                        order_id=order_id,
                        type=TransactionType.FEE,
                        amount=float(-fee_dec),
                        currency="USD",
                        amount_jpy=fee_amount_jpy,
                        exchange_rate=fee_exchange_rate,
                        date=order_date,
                        sku=None,
                    ))
                    fee_count = 1

            shipping_count = 0
            if order.shipping_cost:
                ship_dec = _decimal(order.shipping_cost)
                if ship_dec > 0:
                    ship_amount_jpy: float | None = None
                    ship_exchange_rate: float | None = None
                    if order_date is not None:
                        try:
                            converted, rate_used, _actual = convert(
                                sess, Decimal(str(ship_dec)), "USD", "JPY", order_date.date()
                            )
                            ship_amount_jpy = float(converted)
                            ship_exchange_rate = float(rate_used)
                        except RateNotFoundError:
                            pass
                    sess.add(Transaction(
                        order_id=order_id,
                        type=TransactionType.SHIPPING,
                        amount=float(ship_dec),
                        currency="USD",
                        amount_jpy=ship_amount_jpy,
                        exchange_rate=ship_exchange_rate,
                        date=order_date,
                        sku=None,
                    ))
                    shipping_count = 1

            sess.flush()
            if owns_session:
                sess.commit()

            return RebuildResult(
                order_id=order_id,
                sale_count=sale_count,
                fee_count=fee_count,
                shipping_count=shipping_count,
                deleted_count=deleted_count,
            )
        except Exception:
            if owns_session:
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
        Batch rebuild across all orders.
        date_from / date_to filter on Order.order_date.
        One order failing does NOT block others — failure goes into skipped_reason.
        """
        sess = self._get_session()
        q = sess.query(Order)
        if date_from:
            q = q.filter(Order.order_date >= date_from)
        if date_to:
            q = q.filter(Order.order_date <= date_to)
        results: list[RebuildResult] = []
        for order in q.all():
            try:
                results.append(
                    self.rebuild_for_order(order.ebay_order_id, overwrite=overwrite)
                )
            except Exception as ex:
                results.append(RebuildResult(
                    order_id=order.ebay_order_id,
                    sale_count=0, fee_count=0, shipping_count=0, deleted_count=0,
                    skipped_reason=f"error: {ex}",
                ))
        return results

    def list_by_order(self, order_id: str) -> list[Transaction]:
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
        sess = self._get_session()
        q = sess.query(Transaction).filter(Transaction.type == tx_type)
        if date_from:
            q = q.filter(Transaction.date >= date_from)
        if date_to:
            q = q.filter(Transaction.date <= date_to)
        return q.order_by(Transaction.id).all()

    def list_by_date_range(
        self, date_from: datetime, date_to: datetime
    ) -> list[Transaction]:
        sess = self._get_session()
        return (
            sess.query(Transaction)
            .filter(Transaction.date >= date_from, Transaction.date <= date_to)
            .order_by(Transaction.id)
            .all()
        )
