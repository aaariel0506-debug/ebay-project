from datetime import date, datetime
from decimal import Decimal

from core.models import ExchangeRate, Order, OrderStatus, Transaction, TransactionType
from core.security.audit import AuditLog
from scripts.backfill_amount_jpy import backfill_transactions


def _order(sess, oid: str, order_date: datetime):
    sess.add(Order(ebay_order_id=oid, sale_price=Decimal("100.00"), shipping_cost=Decimal("0"), ebay_fee=Decimal("0"), buyer_country="US", status=OrderStatus.SHIPPED, order_date=order_date))
    sess.flush()


def test_backfill_dry_run_doesnt_write(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026,4,15), from_currency="USD", to_currency="JPY", rate=Decimal("150"), source="csv"))
    _order(db_session, "ORD-B1", datetime(2026,4,15))
    db_session.add(Transaction(order_id="ORD-B1", type=TransactionType.FEE, amount=-10, currency="USD", date=datetime(2026,4,15)))
    db_session.flush()
    result = backfill_transactions(db_session, dry_run=True, since=None, batch_size=500)
    tx = db_session.query(Transaction).first()
    assert result["updated"] == 1
    assert tx.amount_jpy is None


def test_backfill_fills_only_null_rows(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026,4,15), from_currency="USD", to_currency="JPY", rate=Decimal("150"), source="csv"))
    _order(db_session, "ORD-B2", datetime(2026,4,15))
    db_session.add(Transaction(order_id="ORD-B2", type=TransactionType.FEE, amount=-10, currency="USD", date=datetime(2026,4,15), amount_jpy=-1500))
    db_session.add(Transaction(order_id="ORD-B2", type=TransactionType.SHIPPING, amount=10, currency="USD", date=datetime(2026,4,15)))
    db_session.flush()
    result = backfill_transactions(db_session, dry_run=False, since=None, batch_size=500)
    assert result["updated"] == 1
    assert result["audit_batches"] == 1
    audit = db_session.query(AuditLog).filter(AuditLog.action == "finance.backfill_amount_jpy.batch").one()
    assert audit.detail["batch_size"] == 1


def test_backfill_skips_when_no_rate(db_session):
    _order(db_session, "ORD-B3", datetime(2026,4,15))
    db_session.add(Transaction(order_id="ORD-B3", type=TransactionType.FEE, amount=-10, currency="USD", date=datetime(2026,4,15)))
    db_session.flush()
    result = backfill_transactions(db_session, dry_run=False, since=None, batch_size=500)
    assert result["skipped"] == 1


def test_backfill_recomputes_profit_for_sale_type(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026,4,15), from_currency="USD", to_currency="JPY", rate=Decimal("150"), source="csv"))
    _order(db_session, "ORD-B4", datetime(2026,4,15))
    db_session.add(Transaction(order_id="ORD-B4", sku="SKU-1", type=TransactionType.SALE, amount=100, currency="USD", date=datetime(2026,4,15), total_cost=5000))
    db_session.flush()
    result = backfill_transactions(db_session, dry_run=False, since=None, batch_size=500)
    tx = db_session.query(Transaction).first()
    assert result["updated"] == 1
    assert Decimal(str(tx.profit)) == Decimal("10000.0")


def test_backfill_is_idempotent(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026,4,15), from_currency="USD", to_currency="JPY", rate=Decimal("150"), source="csv"))
    _order(db_session, "ORD-B5", datetime(2026,4,15))
    db_session.add(Transaction(order_id="ORD-B5", type=TransactionType.FEE, amount=-10, currency="USD", date=datetime(2026,4,15)))
    db_session.flush()
    first = backfill_transactions(db_session, dry_run=False, since=None, batch_size=500)
    second = backfill_transactions(db_session, dry_run=False, since=None, batch_size=500)
    assert first["updated"] == 1
    assert second["updated"] == 0


def test_backfill_dry_run_does_not_write_audit_log(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 4, 15), from_currency="USD", to_currency="JPY", rate=Decimal("150"), source="csv"))
    _order(db_session, "ORD-B6", datetime(2026, 4, 15))
    db_session.add(Transaction(order_id="ORD-B6", type=TransactionType.FEE, amount=-10, currency="USD", date=datetime(2026, 4, 15)))
    db_session.flush()
    result = backfill_transactions(db_session, dry_run=True, since=None, batch_size=500)
    assert result["audit_batches"] == 0
    assert db_session.query(AuditLog).count() == 0
