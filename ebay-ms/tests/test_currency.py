from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from core.models import ExchangeRate, Product, ProductStatus, Transaction, TransactionType
from core.utils.currency import RateNotFoundError, convert, get_exchange_rate, import_rates_from_csv
from modules.finance.order_sync_service import OrderSyncService
from modules.finance.transaction_service import TransactionService


def test_exact_date_hit(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 15), from_currency="USD", to_currency="JPY", rate=Decimal("149.850000"), source="csv"))
    db_session.flush()
    rate, actual = get_exchange_rate(db_session, "USD", "JPY", date(2026, 3, 15))
    assert rate == Decimal("149.850000")
    assert actual == date(2026, 3, 15)


def test_fallback_to_previous_day(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 14), from_currency="USD", to_currency="JPY", rate=Decimal("150.000000"), source="csv"))
    db_session.flush()
    rate, actual = get_exchange_rate(db_session, "USD", "JPY", date(2026, 3, 15))
    assert rate == Decimal("150.000000")
    assert actual == date(2026, 3, 14)


def test_fallback_within_7_days(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 8), from_currency="USD", to_currency="JPY", rate=Decimal("148.000000"), source="csv"))
    db_session.flush()
    rate, actual = get_exchange_rate(db_session, "USD", "JPY", date(2026, 3, 15))
    assert rate == Decimal("148.000000")
    assert actual == date(2026, 3, 8)


def test_fallback_beyond_7_days_raises(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 1), from_currency="USD", to_currency="JPY", rate=Decimal("150"), source="csv"))
    db_session.flush()
    with pytest.raises(RateNotFoundError):
        get_exchange_rate(db_session, "USD", "JPY", date(2026, 3, 15))


def test_same_currency_returns_one(db_session):
    rate, actual = get_exchange_rate(db_session, "USD", "USD", date(2026, 3, 15))
    assert rate == Decimal("1.0")
    assert actual == date(2026, 3, 15)


def test_multiple_currencies_no_cross_talk(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 15), from_currency="EUR", to_currency="JPY", rate=Decimal("160"), source="csv"))
    db_session.flush()
    with pytest.raises(RateNotFoundError):
        get_exchange_rate(db_session, "USD", "JPY", date(2026, 3, 15))


def test_convert_preserves_decimal_precision(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 15), from_currency="JPY", to_currency="USD", rate=Decimal("0.006680"), source="csv"))
    db_session.flush()
    amount, rate, _ = convert(db_session, Decimal("1000"), "JPY", "USD", date(2026, 3, 15))
    assert amount == Decimal("6.680000")
    assert rate == Decimal("0.006680")


def test_convert_returns_tuple_amount_rate_date(db_session):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 15), from_currency="USD", to_currency="JPY", rate=Decimal("149.850000"), source="csv"))
    db_session.flush()
    amount, rate, actual = convert(db_session, Decimal("2"), "USD", "JPY", date(2026, 3, 15))
    assert amount == Decimal("299.700000")
    assert rate == Decimal("149.850000")
    assert actual == date(2026, 3, 15)


def test_convert_same_currency_passes_through(db_session):
    amount, rate, actual = convert(db_session, Decimal("123.45"), "JPY", "JPY", date(2026, 3, 15))
    assert amount == Decimal("123.45")
    assert rate == Decimal("1.0")
    assert actual == date(2026, 3, 15)


def test_import_valid_csv_inserts_rows(db_session, tmp_path):
    p = tmp_path / "rates.csv"
    p.write_text("rate_date,from_currency,to_currency,rate\n2026-03-15,USD,JPY,149.85\n", encoding="utf-8")
    result = import_rates_from_csv(db_session, str(p))
    assert result["created"] == 1
    assert db_session.query(ExchangeRate).count() == 1


def test_import_dry_run_does_not_write(db_session, tmp_path):
    p = tmp_path / "rates.csv"
    p.write_text("rate_date,from_currency,to_currency,rate\n2026-03-15,USD,JPY,149.85\n", encoding="utf-8")
    result = import_rates_from_csv(db_session, str(p), dry_run=True)
    assert result["rows_valid"] == 1
    assert db_session.query(ExchangeRate).count() == 0


def test_import_upsert_existing_date(db_session, tmp_path):
    db_session.add(ExchangeRate(rate_date=date(2026, 3, 15), from_currency="USD", to_currency="JPY", rate=Decimal("149.00"), source="csv"))
    db_session.flush()
    p = tmp_path / "rates.csv"
    p.write_text("rate_date,from_currency,to_currency,rate\n2026-03-15,USD,JPY,150.00\n", encoding="utf-8")
    result = import_rates_from_csv(db_session, str(p))
    assert result["updated"] == 1
    row = db_session.query(ExchangeRate).first()
    assert Decimal(str(row.rate)) == Decimal("150.000000")


def test_import_invalid_rows_dont_block_valid(db_session, tmp_path):
    p = tmp_path / "rates.csv"
    p.write_text("rate_date,from_currency,to_currency,rate\n2026-03-15,USD,JPY,149.85\n03/15/2026,USD,JPY,149.85\n", encoding="utf-8")
    result = import_rates_from_csv(db_session, str(p))
    assert result["created"] == 1
    assert result["rows_invalid"] == 1


def test_import_rejects_negative_rate(db_session, tmp_path):
    p = tmp_path / "rates.csv"
    p.write_text("rate_date,from_currency,to_currency,rate\n2026-03-15,USD,JPY,-1\n", encoding="utf-8")
    result = import_rates_from_csv(db_session, str(p), dry_run=True)
    assert result["rows_invalid"] == 1


def test_import_rejects_nonstandard_currency(db_session, tmp_path):
    p = tmp_path / "rates.csv"
    p.write_text("rate_date,from_currency,to_currency,rate\n2026-03-15,usd,JPY,149.85\n", encoding="utf-8")
    result = import_rates_from_csv(db_session, str(p), dry_run=True)
    assert result["rows_invalid"] == 1


class TestCurrencyIntegration:
    def _mock_client(self, pages):
        client = MagicMock()
        pages_iter = iter(pages)
        def fake_get(path: str, **kwargs):
            if "finances" in path:
                return {"transactions": []}
            return next(pages_iter)
        client.get.side_effect = fake_get
        return client

    def test_order_sync_fills_amount_jpy_and_profit_in_jpy(self, db_session):
        db_session.add(ExchangeRate(rate_date=date(2026, 4, 15), from_currency="USD", to_currency="JPY", rate=Decimal("150.000000"), source="csv"))
        db_session.add(Product(sku="SKU-1", title="p", cost_price=Decimal("5000.00"), cost_currency="JPY", status=ProductStatus.ACTIVE, supplier="x"))
        db_session.flush()
        api_data = {"orders": [{"orderId": "ORD-CUR-1", "creationDate": "2026-04-15T10:00:00Z", "orderFulfillmentStatus": {"status": "COMPLETED"}, "buyerCountry": "US", "shippingAddress": {}, "lineItems": [{"sku": "SKU-1", "quantity": 1, "lineItemCost": {"currency": "USD", "value": "100.00"}}], "pricingSummary": {"priceSubtotal": {"value": "100.00", "currency": "USD"}, "total": {"value": "100.00", "currency": "USD"}}, "totalMarketplaceFee": {"value": "0", "currency": "USD"}, "paymentSummary": {"totalDueSeller": {"value": "0", "currency": "USD"}}, "properties": {"soldViaAdCampaign": False}}]}
        svc = OrderSyncService(client=self._mock_client([api_data]))
        import core.database.connection as conn_module
        orig = conn_module.get_session
        conn_module.get_session = lambda: db_session
        orig_commit = db_session.commit
        db_session.commit = lambda *a, **k: None
        try:
            svc.sync_orders(date_from=datetime(2026,4,1), date_to=datetime(2026,4,20))
        finally:
            conn_module.get_session = orig
            db_session.commit = orig_commit
        tx = db_session.query(Transaction).filter(Transaction.order_id == "ORD-CUR-1", Transaction.type == TransactionType.SALE).first()
        assert Decimal(str(tx.amount_jpy)) == Decimal("15000.0000")
        assert Decimal(str(tx.profit)) == Decimal("10000.0000")
        assert round(float(tx.margin), 3) == 0.667

    def test_order_sync_without_rate_leaves_fields_null(self, db_session):
        db_session.add(Product(sku="SKU-2", title="p", cost_price=Decimal("5000.00"), cost_currency="JPY", status=ProductStatus.ACTIVE, supplier="x"))
        db_session.flush()
        api_data = {"orders": [{"orderId": "ORD-CUR-2", "creationDate": "2026-04-15T10:00:00Z", "orderFulfillmentStatus": {"status": "COMPLETED"}, "buyerCountry": "US", "shippingAddress": {}, "lineItems": [{"sku": "SKU-2", "quantity": 1, "lineItemCost": {"currency": "USD", "value": "100.00"}}], "pricingSummary": {"priceSubtotal": {"value": "100.00", "currency": "USD"}, "total": {"value": "100.00", "currency": "USD"}}, "totalMarketplaceFee": {"value": "0", "currency": "USD"}, "paymentSummary": {"totalDueSeller": {"value": "0", "currency": "USD"}}, "properties": {"soldViaAdCampaign": False}}]}
        svc = OrderSyncService(client=self._mock_client([api_data]))
        import core.database.connection as conn_module
        orig = conn_module.get_session
        conn_module.get_session = lambda: db_session
        orig_commit = db_session.commit
        db_session.commit = lambda *a, **k: None
        try:
            svc.sync_orders(date_from=datetime(2026,4,1), date_to=datetime(2026,4,20))
        finally:
            conn_module.get_session = orig
            db_session.commit = orig_commit
        tx = db_session.query(Transaction).filter(Transaction.order_id == "ORD-CUR-2", Transaction.type == TransactionType.SALE).first()
        assert tx.amount_jpy is None
        assert tx.exchange_rate is None

    def test_rebuild_reapplies_current_rate_not_historical(self, db_session):
        db_session.add(ExchangeRate(rate_date=date(2026, 4, 15), from_currency="USD", to_currency="JPY", rate=Decimal("150.000000"), source="csv"))
        db_session.add(Product(sku="SKU-3", title="p", cost_price=Decimal("5000.00"), cost_currency="JPY", status=ProductStatus.ACTIVE, supplier="x"))
        db_session.flush()
        api_data = {"orders": [{"orderId": "ORD-CUR-3", "creationDate": "2026-04-15T10:00:00Z", "orderFulfillmentStatus": {"status": "COMPLETED"}, "buyerCountry": "US", "shippingAddress": {}, "lineItems": [{"sku": "SKU-3", "quantity": 1, "lineItemCost": {"currency": "USD", "value": "100.00"}}], "pricingSummary": {"priceSubtotal": {"value": "100.00", "currency": "USD"}, "total": {"value": "100.00", "currency": "USD"}}, "totalMarketplaceFee": {"value": "0", "currency": "USD"}, "paymentSummary": {"totalDueSeller": {"value": "0", "currency": "USD"}}, "properties": {"soldViaAdCampaign": False}}]}
        svc = OrderSyncService(client=self._mock_client([api_data]))
        import core.database.connection as conn_module
        orig = conn_module.get_session
        conn_module.get_session = lambda: db_session
        orig_commit = db_session.commit
        db_session.commit = lambda *a, **k: None
        try:
            svc.sync_orders(date_from=datetime(2026,4,1), date_to=datetime(2026,4,20))
        finally:
            conn_module.get_session = orig
            db_session.commit = orig_commit
        row = db_session.query(ExchangeRate).filter(ExchangeRate.rate_date == date(2026, 4, 15)).first()
        row.rate = Decimal("151.000000")
        db_session.flush()
        TransactionService(session=db_session).rebuild_for_order("ORD-CUR-3")
        tx = db_session.query(Transaction).filter(Transaction.order_id == "ORD-CUR-3", Transaction.type == TransactionType.SALE).first()
        assert Decimal(str(tx.amount_jpy)) == Decimal("15100.0000")
