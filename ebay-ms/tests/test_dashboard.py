from datetime import datetime
from decimal import Decimal

from core.models import Order, OrderItem, OrderStatus, Product, ProductStatus, Transaction, TransactionType
from modules.finance.dashboard import UNCAPTURED_ITEMS, DashboardService, DateRange, format_dashboard


def _product(db_session, sku: str, title: str = "P"):
    db_session.add(Product(sku=sku, title=title, cost_price=Decimal("100"), cost_currency="JPY", status=ProductStatus.ACTIVE, supplier="x"))
    db_session.flush()


def _order(db_session, oid: str, when: datetime):
    db_session.add(Order(ebay_order_id=oid, sale_price=Decimal("0"), shipping_cost=Decimal("0"), ebay_fee=Decimal("0"), buyer_country="US", status=OrderStatus.SHIPPED, order_date=when))
    db_session.flush()


def _item(db_session, oid: str, sku: str, qty: int, sale_amount: str):
    db_session.add(OrderItem(order_id=oid, sku=sku, quantity=qty, unit_price=Decimal("1"), sale_amount=Decimal(sale_amount)))
    db_session.flush()


def _tx(db_session, oid: str, type_: TransactionType, amount_jpy=None, total_cost=None, sku=None, when=None, profit=None):
    db_session.add(Transaction(order_id=oid, sku=sku, type=type_, amount=0, currency="USD", amount_jpy=amount_jpy, total_cost=total_cost, date=when or datetime(2026, 4, 15, 10), profit=profit))
    db_session.flush()


class TestAggregateMetrics:
    def test_empty_database_returns_zeros(self, db_session):
        r = DashboardService(db_session).compute()
        assert r.total_revenue_jpy == Decimal("0")
        assert r.total_cost_jpy == Decimal("0")
        assert r.total_fee_jpy == Decimal("0")
        assert r.gross_profit_jpy == Decimal("0")
        assert r.gross_margin is None

    def test_single_order_all_invariants(self, db_session):
        _product(db_session, "SKU1")
        _order(db_session, "O1", datetime(2026, 4, 15, 10))
        _item(db_session, "O1", "SKU1", 1, "100")
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=15000, total_cost=5000, sku="SKU1")
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-1500)
        _tx(db_session, "O1", TransactionType.SHIPPING, amount_jpy=500)
        r = DashboardService(db_session).compute()
        assert r.total_revenue_jpy == Decimal("15500")
        assert r.total_cost_jpy == Decimal("5000")
        assert r.total_fee_jpy == Decimal("1500")
        assert r.gross_profit_jpy == Decimal("9000")
        assert round(r.gross_margin, 3) == 0.581

    def test_multiple_orders_sums_correctly(self, db_session):
        for i in range(2):
            _product(db_session, f"SKU{i}")
            _order(db_session, f"O{i}", datetime(2026, 4, 15, 10))
            _item(db_session, f"O{i}", f"SKU{i}", 1, "100")
        _tx(db_session, "O0", TransactionType.SALE, amount_jpy=1000, total_cost=200, sku="SKU0")
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=2000, total_cost=500, sku="SKU1")
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-100)
        r = DashboardService(db_session).compute()
        assert r.total_revenue_jpy == Decimal("3000")
        assert r.total_cost_jpy == Decimal("700")
        assert r.total_fee_jpy == Decimal("100")
        assert r.gross_profit_jpy == Decimal("2200")

    def test_refund_reduces_revenue(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=10000)
        _tx(db_session, "O1", TransactionType.REFUND, amount_jpy=-3000)
        r = DashboardService(db_session).compute()
        assert r.total_revenue_jpy == Decimal("7000")

    def test_adjustment_excluded_from_all_sums(self, db_session):
        _tx(db_session, "O1", TransactionType.ADJUSTMENT, amount_jpy=9999, total_cost=8888)
        r = DashboardService(db_session).compute()
        assert r.total_revenue_jpy == Decimal("0")
        assert r.total_cost_jpy == Decimal("0")
        assert r.total_fee_jpy == Decimal("0")

    def test_null_amount_jpy_goes_to_uncovered(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=None, total_cost=500)
        r = DashboardService(db_session).compute()
        assert r.uncovered_transactions == 1
        assert r.total_revenue_jpy == Decimal("0")

    def test_fee_is_reported_as_positive_absolute(self, db_session):
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-1500)
        r = DashboardService(db_session).compute()
        assert r.total_fee_jpy == Decimal("1500")

    def test_does_not_sum_transaction_profit_field(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, total_cost=300, profit=99999)
        r = DashboardService(db_session).compute()
        assert r.gross_profit_jpy == Decimal("700")

    def test_uncaptured_items_constant_exposed(self, db_session):
        r = DashboardService(db_session).compute()
        assert r.uncaptured_items == UNCAPTURED_ITEMS


class TestDateFilter:
    def test_date_range_start_filter(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 4, 1, 10))
        _tx(db_session, "O2", TransactionType.SALE, amount_jpy=2000, when=datetime(2026, 4, 20, 10))
        r = DashboardService(db_session).compute(date_range=DateRange(start=datetime(2026, 4, 15)))
        assert r.total_revenue_jpy == Decimal("2000")

    def test_date_range_end_is_exclusive(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 4, 15, 0))
        _tx(db_session, "O2", TransactionType.SALE, amount_jpy=2000, when=datetime(2026, 4, 16, 0))
        r = DashboardService(db_session).compute(date_range=DateRange(end=datetime(2026, 4, 16, 0)))
        assert r.total_revenue_jpy == Decimal("1000")

    def test_none_date_range_returns_all_time(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000)
        r = DashboardService(db_session).compute(date_range=None)
        assert r.total_revenue_jpy == Decimal("1000")

    def test_this_month_helper_boundary(self, db_session):
        dr = DashboardService.this_month()
        assert dr.start.day == 1
        assert dr.end > dr.start


class TestTopAnalysis:
    def test_top_profit_skus_ordered_desc(self, db_session):
        for sku, revenue, cost in [("A", 1000, 100), ("B", 800, 100), ("C", 700, 200)]:
            _product(db_session, sku, sku)
            _order(db_session, f"O{sku}", datetime(2026, 4, 15, 10))
            _item(db_session, f"O{sku}", sku, 1, "1")
            _tx(db_session, f"O{sku}", TransactionType.SALE, amount_jpy=revenue, total_cost=cost, sku=sku)
        r = DashboardService(db_session).compute()
        assert [x.sku for x in r.top_profit_skus[:3]] == ["A", "B", "C"]

    def test_top_loss_skus_only_negative(self, db_session):
        for sku, revenue, cost in [("A", 1000, 100), ("B", 1000, 1200), ("C", 1000, 1300), ("D", 1000, 200), ("E", 1000, 300)]:
            _product(db_session, sku, sku)
            _order(db_session, f"O{sku}", datetime(2026, 4, 15, 10))
            _item(db_session, f"O{sku}", sku, 1, "1")
            _tx(db_session, f"O{sku}", TransactionType.SALE, amount_jpy=revenue, total_cost=cost, sku=sku)
        r = DashboardService(db_session).compute()
        assert [x.sku for x in r.top_loss_skus] == ["C", "B"]

    def test_top_loss_empty_when_all_profitable(self, db_session):
        _product(db_session, "A", "A")
        _order(db_session, "OA", datetime(2026, 4, 15, 10))
        _item(db_session, "OA", "A", 1, "1")
        _tx(db_session, "OA", TransactionType.SALE, amount_jpy=1000, total_cost=100, sku="A")
        r = DashboardService(db_session).compute()
        assert r.top_loss_skus == []

    def test_top_units_sold_uses_order_items_quantity(self, db_session):
        for sku, qty in [("A", 2), ("B", 5)]:
            _product(db_session, sku, sku)
            _order(db_session, f"O{sku}", datetime(2026, 4, 15, 10))
            _item(db_session, f"O{sku}", sku, qty, "1")
            _tx(db_session, f"O{sku}", TransactionType.SALE, amount_jpy=1000, total_cost=100, sku=sku)
        r = DashboardService(db_session).compute()
        assert r.top_units_skus[0].sku == "B"
        assert r.top_units_skus[0].units_sold == 5


class TestDerivedMetrics:
    def test_avg_order_margin_is_mean_not_sum_based(self, db_session):
        for oid, revenue, cost in [("OA", 1000, 200), ("OB", 2000, 1600)]:
            _order(db_session, oid, datetime(2026, 4, 15, 10))
            _tx(db_session, oid, TransactionType.SALE, amount_jpy=revenue, total_cost=cost)
        r = DashboardService(db_session).compute()
        assert r.avg_order_margin == 0.5
        assert r.gross_profit_jpy / r.total_revenue_jpy != Decimal("0.5")

    def test_avg_order_margin_skips_zero_revenue_orders(self, db_session):
        _order(db_session, "OA", datetime(2026, 4, 15, 10))
        _tx(db_session, "OA", TransactionType.SALE, amount_jpy=1000, total_cost=500)
        _order(db_session, "OB", datetime(2026, 4, 15, 10))
        _tx(db_session, "OB", TransactionType.FEE, amount_jpy=-300)
        r = DashboardService(db_session).compute()
        assert r.avg_order_margin == 0.5


class TestCoverageReport:
    def test_coverage_ratio_calculation(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000)
        _tx(db_session, "O2", TransactionType.SALE, amount_jpy=None)
        r = DashboardService(db_session).compute()
        assert r.coverage_ratio == 0.5


class TestFormatOutput:
    def test_format_dashboard_contains_uncaptured_warning(self, db_session):
        r = DashboardService(db_session).compute()
        text = format_dashboard(r)
        assert "未采集" in text
        assert "sales_tax" in text
        assert "shipping_actual" in text
