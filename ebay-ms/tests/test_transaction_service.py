"""Day 27: TransactionService tests."""

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from core.models import (
    ExchangeRate,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductStatus,
    Transaction,
    TransactionType,
)
from modules.finance.order_sync_service import OrderSyncService
from modules.finance.transaction_service import TransactionService


class TestTransactionService:
    @staticmethod
    def _make_product(sess, sku: str, cost_price: str | None):
        prod = Product(
            sku=sku,
            title=f"Product {sku}",
            cost_price=Decimal(cost_price) if cost_price is not None else None,
            cost_currency="USD",
            status=ProductStatus.ACTIVE,
            supplier="Test Supplier",
        )
        sess.add(prod)
        sess.flush()
        return prod

    @staticmethod
    def _make_order(sess, order_id: str, *, sale_price: str, ebay_fee: str, shipping_cost: str, order_date: datetime | None = None):
        order_dt = order_date or datetime(2026, 4, 21, 10, 0, 0)
        existing_rate = sess.query(ExchangeRate).filter(
            ExchangeRate.rate_date == order_dt.date(),
            ExchangeRate.from_currency == "USD",
            ExchangeRate.to_currency == "JPY",
        ).first()
        if existing_rate is None:
            sess.add(ExchangeRate(rate_date=order_dt.date(), from_currency="USD", to_currency="JPY", rate=Decimal("150.000000"), source="csv"))
            sess.flush()
        order = Order(
            ebay_order_id=order_id,
            sale_price=Decimal(sale_price),
            ebay_fee=Decimal(ebay_fee),
            shipping_cost=Decimal(shipping_cost),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            order_date=order_dt,
            buyer_name="Tester",
            shipping_address="US",
        )
        sess.add(order)
        sess.flush()
        return order

    @staticmethod
    def _make_order_item(sess, order_id: str, sku: str, *, sale_amount: str, quantity: int, unit_price: str | None = None):
        amt = Decimal(sale_amount)
        qty = quantity or 1
        oi = OrderItem(
            order_id=order_id,
            sku=sku,
            quantity=qty,
            unit_price=Decimal(unit_price) if unit_price is not None else (amt / qty),
            sale_amount=amt,
        )
        sess.add(oi)
        sess.flush()
        return oi

    def test_rebuild_single_order_writes_sale_fee_shipping(self, db_session):
        self._make_product(db_session, "SKU-A", "10.00")
        self._make_product(db_session, "SKU-B", "20.00")
        self._make_order(db_session, "ORD-001", sale_price="110.00", ebay_fee="13.00", shipping_cost="8.00")
        self._make_order_item(db_session, "ORD-001", "SKU-A", sale_amount="50.00", quantity=1)
        self._make_order_item(db_session, "ORD-001", "SKU-B", sale_amount="60.00", quantity=2)

        result = TransactionService(session=db_session).rebuild_for_order("ORD-001")
        rows = db_session.query(Transaction).filter(Transaction.order_id == "ORD-001").all()

        assert result.sale_count == 2
        assert result.fee_count == 1
        assert result.shipping_count == 1
        assert len(rows) == 4

    def test_rebuild_preserves_conservation_invariants(self, db_session):
        self._make_product(db_session, "SKU-A", "10.00")
        self._make_product(db_session, "SKU-B", "20.00")
        order = self._make_order(db_session, "ORD-INV", sale_price="110.00", ebay_fee="13.00", shipping_cost="8.00")
        self._make_order_item(db_session, "ORD-INV", "SKU-A", sale_amount="50.00", quantity=1)
        self._make_order_item(db_session, "ORD-INV", "SKU-B", sale_amount="60.00", quantity=2)

        TransactionService(session=db_session).rebuild_for_order("ORD-INV")
        rows = db_session.query(Transaction).filter(Transaction.order_id == "ORD-INV").all()
        sales = [r for r in rows if r.type == TransactionType.SALE]
        fees = [r for r in rows if r.type == TransactionType.FEE]
        shipping = [r for r in rows if r.type == TransactionType.SHIPPING]

        assert sum(Decimal(str(r.amount)) for r in sales) == Decimal(str(order.sale_price))
        assert sum(Decimal(str(r.amount)) for r in fees) == Decimal(str(-order.ebay_fee))
        assert sum(Decimal(str(r.amount)) for r in shipping) == Decimal(str(order.shipping_cost))
        assert len(sales) == db_session.query(OrderItem).filter(OrderItem.order_id == "ORD-INV").count()
        assert len(fees) <= 1
        assert len(shipping) <= 1

    def test_rebuild_sale_populates_cost_profit_margin(self, db_session):
        self._make_product(db_session, "SKU-COST", "30.00")
        self._make_order(db_session, "ORD-COST", sale_price="100.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(db_session, "ORD-COST", "SKU-COST", sale_amount="100.00", quantity=1)

        TransactionService(session=db_session).rebuild_for_order("ORD-COST")
        sale = db_session.query(Transaction).filter(Transaction.order_id == "ORD-COST", Transaction.type == TransactionType.SALE).first()

        assert sale is not None
        assert Decimal(str(sale.unit_cost)) == Decimal("30.00")
        assert Decimal(str(sale.total_cost)) == Decimal("30.0000")
        assert Decimal(str(sale.amount_jpy)) == Decimal("15000.0000")
        assert Decimal(str(sale.profit)) == Decimal("14970.0000")
        assert Decimal(str(sale.margin)).quantize(Decimal("0.0001")) == Decimal("0.9980")

    def test_rebuild_sale_handles_missing_product(self, db_session):
        self._make_order(db_session, "ORD-MISS", sale_price="50.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(db_session, "ORD-MISS", "SKU-MISS", sale_amount="50.00", quantity=1, unit_price="50.00")

        TransactionService(session=db_session).rebuild_for_order("ORD-MISS")
        sale = db_session.query(Transaction).filter(Transaction.order_id == "ORD-MISS", Transaction.type == TransactionType.SALE).first()

        assert sale is not None
        assert sale.unit_cost is None
        assert sale.total_cost is None
        assert sale.profit is None
        assert sale.margin is None

    def test_rebuild_overwrite_true_replaces_old_transactions(self, db_session):
        self._make_product(db_session, "SKU-OVR", "10.00")
        self._make_order(db_session, "ORD-OVR", sale_price="50.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(db_session, "ORD-OVR", "SKU-OVR", sale_amount="50.00", quantity=1)
        svc = TransactionService(session=db_session)
        svc.rebuild_for_order("ORD-OVR")
        sale = db_session.query(Transaction).filter(Transaction.order_id == "ORD-OVR", Transaction.type == TransactionType.SALE).first()
        sale.amount = Decimal("999.00")
        db_session.flush()

        result = svc.rebuild_for_order("ORD-OVR", overwrite=True)
        sale2 = db_session.query(Transaction).filter(Transaction.order_id == "ORD-OVR", Transaction.type == TransactionType.SALE).first()
        assert result.deleted_count > 0
        assert Decimal(str(sale2.amount)) == Decimal("50.00")

    def test_rebuild_overwrite_false_skips_when_exists(self, db_session):
        self._make_product(db_session, "SKU-SKIP", "10.00")
        self._make_order(db_session, "ORD-SKIP", sale_price="50.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(db_session, "ORD-SKIP", "SKU-SKIP", sale_amount="50.00", quantity=1)
        svc = TransactionService(session=db_session)
        svc.rebuild_for_order("ORD-SKIP")
        result = svc.rebuild_for_order("ORD-SKIP", overwrite=False)
        assert result.skipped_reason == "already_has_transactions"

    def test_rebuild_zero_fee_no_fee_transaction(self, db_session):
        self._make_product(db_session, "SKU-F0", "10.00")
        self._make_order(db_session, "ORD-F0", sale_price="50.00", ebay_fee="0", shipping_cost="5.00")
        self._make_order_item(db_session, "ORD-F0", "SKU-F0", sale_amount="50.00", quantity=1)
        result = TransactionService(session=db_session).rebuild_for_order("ORD-F0")
        assert result.fee_count == 0
        assert db_session.query(Transaction).filter(Transaction.order_id == "ORD-F0", Transaction.type == TransactionType.FEE).count() == 0

    def test_rebuild_zero_shipping_no_shipping_transaction(self, db_session):
        self._make_product(db_session, "SKU-S0", "10.00")
        self._make_order(db_session, "ORD-S0", sale_price="50.00", ebay_fee="5.00", shipping_cost="0")
        self._make_order_item(db_session, "ORD-S0", "SKU-S0", sale_amount="50.00", quantity=1)
        result = TransactionService(session=db_session).rebuild_for_order("ORD-S0")
        assert result.shipping_count == 0
        assert db_session.query(Transaction).filter(Transaction.order_id == "ORD-S0", Transaction.type == TransactionType.SHIPPING).count() == 0

    def test_rebuild_preserves_refund_transactions(self, db_session):
        self._make_product(db_session, "SKU-R", "10.00")
        self._make_order(db_session, "ORD-R", sale_price="50.00", ebay_fee="5.00", shipping_cost="2.00")
        self._make_order_item(db_session, "ORD-R", "SKU-R", sale_amount="50.00", quantity=1)
        db_session.add(Transaction(order_id="ORD-R", sku="SKU-R", type=TransactionType.REFUND, amount=-10.0, currency="USD", date=datetime(2026,4,21)))
        db_session.flush()

        TransactionService(session=db_session).rebuild_for_order("ORD-R")
        assert db_session.query(Transaction).filter(Transaction.order_id == "ORD-R", Transaction.type == TransactionType.REFUND).count() == 1

    def test_rebuild_order_not_found_raises(self, db_session):
        with pytest.raises(ValueError, match="order_not_found"):
            TransactionService(session=db_session).rebuild_for_order("ORD-NOPE")

    def test_rebuild_order_without_line_items_returns_skipped(self, db_session):
        self._make_order(db_session, "ORD-EMPTY", sale_price="0", ebay_fee="0", shipping_cost="0")
        result = TransactionService(session=db_session).rebuild_for_order("ORD-EMPTY")
        assert result.skipped_reason == "no_order_items"
        assert db_session.query(Transaction).filter(Transaction.order_id == "ORD-EMPTY").count() == 0

    def test_rebuild_all_one_order_fails_others_succeed(self, db_session):
        self._make_product(db_session, "SKU-1", "10.00")
        self._make_product(db_session, "SKU-2", "10.00")
        self._make_order(db_session, "ORD-1", sale_price="10", ebay_fee="0", shipping_cost="0")
        self._make_order(db_session, "ORD-2", sale_price="20", ebay_fee="0", shipping_cost="0")
        self._make_order(db_session, "ORD-3", sale_price="30", ebay_fee="0", shipping_cost="0")
        self._make_order_item(db_session, "ORD-1", "SKU-1", sale_amount="10", quantity=1)
        self._make_order_item(db_session, "ORD-2", "SKU-2", sale_amount="20", quantity=1)
        self._make_order_item(db_session, "ORD-3", "SKU-2", sale_amount="30", quantity=1)

        svc = TransactionService(session=db_session)
        original = svc.rebuild_for_order

        def fake_rebuild(order_id, overwrite=True):
            if order_id == "ORD-2":
                raise RuntimeError("boom")
            return original(order_id, overwrite=overwrite)

        with patch.object(svc, "rebuild_for_order", side_effect=fake_rebuild):
            results = svc.rebuild_all()

        assert len(results) == 3
        assert any(r.order_id == "ORD-2" and r.skipped_reason == "error: boom" for r in results)
        assert db_session.query(Transaction).filter(Transaction.order_id == "ORD-1", Transaction.type == TransactionType.SALE).count() == 1
        assert db_session.query(Transaction).filter(Transaction.order_id == "ORD-3", Transaction.type == TransactionType.SALE).count() == 1

    def test_list_by_order_returns_all_types_ordered_by_id(self, db_session):
        self._make_product(db_session, "SKU-L1", "10.00")
        self._make_order(db_session, "ORD-L1", sale_price="50", ebay_fee="5", shipping_cost="2")
        self._make_order_item(db_session, "ORD-L1", "SKU-L1", sale_amount="50", quantity=1)
        svc = TransactionService(session=db_session)
        svc.rebuild_for_order("ORD-L1")
        rows = svc.list_by_order("ORD-L1")
        assert [r.id for r in rows] == sorted(r.id for r in rows)
        assert {r.type for r in rows} == {TransactionType.SALE, TransactionType.FEE, TransactionType.SHIPPING}

    def test_list_by_type_with_date_range(self, db_session):
        self._make_product(db_session, "SKU-T1", "10.00")
        self._make_order(db_session, "ORD-T1", sale_price="10", ebay_fee="0", shipping_cost="0", order_date=datetime(2026,4,1))
        self._make_order(db_session, "ORD-T2", sale_price="10", ebay_fee="0", shipping_cost="0", order_date=datetime(2026,5,1))
        self._make_order_item(db_session, "ORD-T1", "SKU-T1", sale_amount="10", quantity=1)
        self._make_order_item(db_session, "ORD-T2", "SKU-T1", sale_amount="10", quantity=1)
        svc = TransactionService(session=db_session)
        svc.rebuild_all()
        rows = svc.list_by_type(TransactionType.SALE, datetime(2026,4,1), datetime(2026,4,30,23,59,59))
        assert [r.order_id for r in rows] == ["ORD-T1"]

    def test_list_by_date_range(self, db_session):
        self._make_product(db_session, "SKU-D1", "10.00")
        self._make_order(db_session, "ORD-D1", sale_price="10", ebay_fee="0", shipping_cost="0", order_date=datetime(2026,4,1))
        self._make_order(db_session, "ORD-D2", sale_price="10", ebay_fee="0", shipping_cost="0", order_date=datetime(2026,5,1))
        self._make_order_item(db_session, "ORD-D1", "SKU-D1", sale_amount="10", quantity=1)
        self._make_order_item(db_session, "ORD-D2", "SKU-D1", sale_amount="10", quantity=1)
        svc = TransactionService(session=db_session)
        svc.rebuild_all()
        rows = svc.list_by_date_range(datetime(2026,4,1), datetime(2026,4,30,23,59,59))
        assert {r.order_id for r in rows} == {"ORD-D1"}


class TestTransactionServiceIntegration:
    @contextmanager
    def _patched_db_session(self, db_session):
        import core.database.connection as conn_module
        orig_get = conn_module.get_session
        orig_commit = db_session.commit
        db_session.commit = lambda *a, **k: None
        conn_module.get_session = lambda: db_session
        try:
            yield
        finally:
            conn_module.get_session = orig_get
            db_session.commit = orig_commit

    def _mock_client(self, pages: list[dict], *, finances_responses: dict | None = None):
        client = MagicMock()
        pages_iter = iter(pages)
        finances = finances_responses or {}

        def fake_get(path: str, **kwargs):
            if "/sell/finances/v1/transaction" in path:
                oid = kwargs.get("params", {}).get("orderId", "")
                return finances.get(oid, {"transactions": []})
            return next(pages_iter)

        client.get.side_effect = fake_get
        return client

    def test_sync_then_rebuild_preserves_sale_amount_contract(self, db_session):
        db_session.add(ExchangeRate(rate_date=datetime(2026, 4, 15).date(), from_currency="USD", to_currency="JPY", rate=Decimal("150.000000"), source="csv"))
        db_session.flush()
        prod = Product(
            sku="SKU-QTY",
            title="Qty Product",
            cost_price=Decimal("10.00"),
            cost_currency="USD",
            status=ProductStatus.ACTIVE,
            supplier="Test Supplier",
        )
        db_session.add(prod)
        db_session.flush()

        api_data = {
            "orders": [{
                "orderId": "ORD-QTY-INT",
                "creationDate": "2026-04-15T10:00:00Z",
                "orderFulfillmentStatus": {"status": "COMPLETED"},
                "buyerCountry": "US",
                "shippingAddress": {},
                "lineItems": [{
                    "sku": "SKU-QTY",
                    "quantity": 3,
                    "lineItemCost": {"currency": "USD", "value": "10.00"},
                }],
                "pricingSummary": {
                    "priceSubtotal": {"value": "30.00", "currency": "USD"},
                    "total": {"value": "30.00", "currency": "USD"},
                },
                "totalMarketplaceFee": {"value": "0", "currency": "USD"},
                "paymentSummary": {"totalDueSeller": {"value": "0", "currency": "USD"}},
                "properties": {"soldViaAdCampaign": False},
            }]
        }

        client = self._mock_client([api_data])
        sync_svc = OrderSyncService(client=client)
        with self._patched_db_session(db_session):
            sync_svc.sync_orders(date_from=datetime(2026,4,1), date_to=datetime(2026,4,20))

        sale_before = db_session.query(Transaction).filter(Transaction.order_id == "ORD-QTY-INT", Transaction.type == TransactionType.SALE).first()
        assert sale_before is not None
        before_amount = Decimal(str(sale_before.amount))
        assert before_amount == Decimal("30.00")

        rebuild = TransactionService(session=db_session)
        rebuild.rebuild_for_order("ORD-QTY-INT", overwrite=True)
        sale_after = db_session.query(Transaction).filter(Transaction.order_id == "ORD-QTY-INT", Transaction.type == TransactionType.SALE).first()
        assert sale_after is not None
        assert Decimal(str(sale_after.amount)) == before_amount
        assert Decimal(str(sale_after.amount_jpy)) == Decimal("4500.0000")
        assert Decimal(str(sale_after.total_cost)) == Decimal("30.0000")
        assert Decimal(str(sale_after.profit)) == Decimal("4470.0000")
