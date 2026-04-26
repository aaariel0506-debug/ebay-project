from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from core.models import Order, OrderItem, OrderStatus, Product, ProductStatus, Transaction, TransactionType
from modules.finance.breakdown import BreakdownService, format_breakdown
from modules.finance.dashboard import DashboardService, DateRange


def _product(db_session, sku: str, title: str = "P"):
    db_session.add(Product(sku=sku, title=title, cost_price=Decimal("100"), cost_currency="JPY", status=ProductStatus.ACTIVE, supplier="x"))
    db_session.flush()


def _order(db_session, oid: str, when: datetime):
    db_session.add(Order(ebay_order_id=oid, sale_price=Decimal("0"), shipping_cost=Decimal("0"), ebay_fee=Decimal("0"), buyer_country="US", status=OrderStatus.SHIPPED, order_date=when))
    db_session.flush()


def _item(db_session, oid: str, sku: str, qty: int, sale_amount: str):
    db_session.add(OrderItem(order_id=oid, sku=sku, quantity=qty, unit_price=Decimal("1"), sale_amount=Decimal(sale_amount)))
    db_session.flush()


def _tx(db_session, oid: str, type_: TransactionType, amount_jpy=None, total_cost=None, sku=None, when=None):
    db_session.add(Transaction(order_id=oid, sku=sku, type=type_, amount=0, currency="USD", amount_jpy=amount_jpy, total_cost=total_cost, date=when or datetime(2026, 4, 15, 10)))
    db_session.flush()


class TestAggregateCorrectness:
    def test_empty_database_returns_empty_rows(self, db_session):
        r = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)))
        assert r.rows == []

    def test_single_month_single_order(self, db_session):
        _product(db_session, "SKU1")
        _order(db_session, "O1", datetime(2026, 4, 15, 10))
        _item(db_session, "O1", "SKU1", 2, "100")
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=15000, total_cost=5000, sku="SKU1", when=datetime(2026, 4, 15, 10))
        _tx(db_session, "O1", TransactionType.SHIPPING, amount_jpy=500, when=datetime(2026, 4, 15, 10))
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-1500, when=datetime(2026, 4, 15, 10))
        row = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))).rows[0]
        assert row.revenue_jpy == Decimal("15500")
        assert row.cost_jpy == Decimal("5000")
        assert row.fee_jpy == Decimal("1500")
        assert row.gross_profit_jpy == Decimal("9000")

    def test_multiple_months_ordered_ascending(self, db_session):
        for idx, month in enumerate([3, 1, 2], start=1):
            _tx(db_session, f"O{idx}", TransactionType.SALE, amount_jpy=idx * 1000, when=datetime(2026, month, 15, 10))
        rows = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 1, 1), datetime(2026, 4, 1))).rows
        assert [r.period for r in rows] == ["2026-01", "2026-02", "2026-03"]

    def test_refund_attributed_to_transaction_date_not_order_date(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=10000, when=datetime(2026, 4, 15, 10))
        _tx(db_session, "O1", TransactionType.REFUND, amount_jpy=-3000, when=datetime(2026, 5, 5, 10))
        rows = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 15), datetime(2026, 6, 1))).rows
        assert len(rows) == 2
        assert rows[0].period == "2026-04" and rows[0].revenue_jpy == Decimal("10000")
        assert rows[1].period == "2026-05" and rows[1].revenue_jpy == Decimal("-3000")

    def test_fee_reported_as_positive_in_each_bucket(self, db_session):
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-1500, when=datetime(2026, 4, 15, 10))
        row = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))).rows[0]
        assert row.fee_jpy == Decimal("1500")

    def test_adjustment_excluded_from_all_buckets(self, db_session):
        _tx(db_session, "O1", TransactionType.ADJUSTMENT, amount_jpy=9999, when=datetime(2026, 4, 15, 10))
        rows = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))).rows
        assert rows[0].revenue_jpy == Decimal("0")
        assert rows[0].cost_jpy == Decimal("0")
        assert rows[0].fee_jpy == Decimal("0")

    def test_null_amount_jpy_counted_as_uncovered_in_its_bucket(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=None, when=datetime(2026, 4, 15, 10))
        row = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))).rows[0]
        assert row.uncovered_transactions == 1

    def test_bucket_gross_margin_matches_per_bucket_formula(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=10000, total_cost=3000, when=datetime(2026, 4, 15, 10))
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-1000, when=datetime(2026, 4, 15, 10))
        row = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))).rows[0]
        assert row.gross_profit_jpy == row.revenue_jpy - row.cost_jpy - row.fee_jpy


class TestBucketBoundaries:
    def test_month_bucket_aligns_to_month_start(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 4, 20, 10))
        row = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 15), datetime(2026, 5, 1))).rows[0]
        assert row.period_start == datetime(2026, 4, 1)

    def test_month_bucket_crosses_year_boundary(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2025, 12, 15, 10))
        _tx(db_session, "O2", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 1, 15, 10))
        rows = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2025, 12, 10), datetime(2026, 2, 1))).rows
        assert [r.period for r in rows] == ["2025-12", "2026-01"]

    def test_day_bucket_single_day_has_one_row(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 4, 15, 10))
        rows = BreakdownService(db_session).compute(group_by="day", date_range=DateRange(datetime(2026, 4, 15), datetime(2026, 4, 16))).rows
        assert len(rows) == 1 and rows[0].period == "2026-04-15"

    def test_end_is_exclusive(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 4, 16, 0, 0))
        rows = BreakdownService(db_session).compute(group_by="day", date_range=DateRange(datetime(2026, 4, 15), datetime(2026, 4, 16))).rows
        assert rows == []

    def test_empty_bucket_is_skipped(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 1, 15, 10))
        _tx(db_session, "O2", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 3, 15, 10))
        rows = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 1, 1), datetime(2026, 4, 1))).rows
        assert [r.period for r in rows] == ["2026-01", "2026-03"]


class TestSemanticConsistency:
    def test_breakdown_sum_equals_dashboard_over_same_range(self, db_session):
        for when, amount, cost, fee in [
            (datetime(2026, 1, 15, 10), 1000, 200, -50),
            (datetime(2026, 2, 15, 10), 2000, 500, -60),
            (datetime(2026, 3, 15, 10), -300, None, None),
        ]:
            _tx(db_session, "O1", TransactionType.SALE if amount > 0 else TransactionType.REFUND, amount_jpy=amount, total_cost=cost, when=when)
            if fee is not None:
                _tx(db_session, "O1", TransactionType.FEE, amount_jpy=fee, when=when)
        dr = DateRange(datetime(2026, 1, 1), datetime(2026, 4, 1))
        breakdown = BreakdownService(db_session).compute(group_by="month", date_range=dr)
        dash = DashboardService(db_session).compute(date_range=dr)
        assert sum((r.revenue_jpy for r in breakdown.rows), Decimal("0")) == dash.total_revenue_jpy
        assert sum((r.cost_jpy for r in breakdown.rows), Decimal("0")) == dash.total_cost_jpy
        assert sum((r.fee_jpy for r in breakdown.rows), Decimal("0")) == dash.total_fee_jpy
        assert sum((r.gross_profit_jpy for r in breakdown.rows), Decimal("0")) == dash.gross_profit_jpy

    def test_dashboard_411_tests_still_pass_with_lean_flags_false(self, db_session):
        r = DashboardService(db_session).compute(date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)), include_sku_analysis=False, include_order_margin=False)
        assert r.avg_order_margin is None

    def test_lean_mode_returns_none_for_avg_order_margin(self, db_session):
        r = DashboardService(db_session).compute(date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)), include_order_margin=False)
        assert r.avg_order_margin is None

    def test_lean_mode_returns_empty_for_top_skus(self, db_session):
        r = DashboardService(db_session).compute(date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)), include_sku_analysis=False)
        assert r.top_profit_skus == [] and r.top_loss_skus == [] and r.top_units_skus == []

    def test_dashboard_compute_with_lean_true_flags_identical_to_default(self, db_session):
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, total_cost=200, when=datetime(2026, 4, 15, 10))
        default = DashboardService(db_session).compute(date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)))
        explicit = DashboardService(db_session).compute(date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)), include_sku_analysis=True, include_order_margin=True)
        assert default == explicit

    def test_bucket_gross_margin_none_when_revenue_zero(self, db_session):
        _tx(db_session, "O1", TransactionType.FEE, amount_jpy=-100, when=datetime(2026, 4, 15, 10))
        row = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))).rows[0]
        assert row.gross_margin is None

    def test_bucket_ordering_independent_of_transaction_insertion_order(self, db_session):
        for when in [datetime(2026, 3, 15, 10), datetime(2026, 1, 15, 10), datetime(2026, 2, 15, 10)]:
            _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=when)
        rows = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 1, 1), datetime(2026, 4, 1))).rows
        assert [r.period for r in rows] == ["2026-01", "2026-02", "2026-03"]


class TestCli:
    def test_cli_breakdown_month_runs_on_empty_db(self, db_session):
        from main import run
        with patch("sys.argv", ["main.py", "finance", "breakdown", "--group-by", "month", "--period", "all"]):
            assert run() == 0

    def test_cli_custom_without_from_to_errors(self, db_session):
        from main import run
        with patch("sys.argv", ["main.py", "finance", "breakdown", "--group-by", "month", "--period", "custom"]):
            with pytest.raises(SystemExit):
                run()

    def test_cli_invalid_group_by_errors(self, db_session):
        from main import run
        with patch("sys.argv", ["main.py", "finance", "breakdown", "--group-by", "week", "--period", "all"]):
            with pytest.raises(SystemExit):
                run()


class TestOutput:
    def test_format_breakdown_contains_uncaptured_warning(self, db_session):
        r = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)))
        text = format_breakdown(r)
        assert "未采集" in text

    def test_format_breakdown_empty_shows_no_data_line(self, db_session):
        r = BreakdownService(db_session).compute(group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1)))
        text = format_breakdown(r)
        assert "(无数据)" in text


class TestAdFee:
    """Day 31-C 新增:AD_FEE 在 breakdown 的呈现。"""

    def test_breakdown_row_has_ad_fee_field(self, db_session):
        """BreakdownRow.ad_fee_jpy 字段必须存在并正确聚合(取绝对值)。"""
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=10000, when=datetime(2026, 4, 15, 10))
        _tx(db_session, "O1", TransactionType.AD_FEE, amount_jpy=-1500, when=datetime(2026, 4, 15, 10))
        rows = BreakdownService(db_session).compute(
            group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))
        ).rows
        assert len(rows) == 1
        assert rows[0].ad_fee_jpy == Decimal("1500")

    def test_breakdown_per_period_gross_profit_subtracts_ad_fee(self, db_session):
        """每个 bucket 的 gross_profit 都要减 AD_FEE,与 dashboard 一致。"""
        _product(db_session, "SKU1")
        _order(db_session, "O1", datetime(2026, 4, 15, 10))
        _item(db_session, "O1", "SKU1", 1, "100")
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=10000, total_cost=3000, sku="SKU1", when=datetime(2026, 4, 15, 10))
        _tx(db_session, "O1", TransactionType.AD_FEE, amount_jpy=-1000, when=datetime(2026, 4, 15, 10))
        rows = BreakdownService(db_session).compute(
            group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))
        ).rows
        # 10000 - 3000 - 0(fee) - 1000(ad_fee) = 6000
        assert rows[0].gross_profit_jpy == Decimal("6000")

    def test_format_breakdown_contains_adfee_column(self, db_session):
        """format_breakdown 表头必须含 AdFee 列,夹在 Fee 和 Profit 之间。"""
        _tx(db_session, "O1", TransactionType.SALE, amount_jpy=1000, when=datetime(2026, 4, 15, 10))
        r = BreakdownService(db_session).compute(
            group_by="month", date_range=DateRange(datetime(2026, 4, 1), datetime(2026, 5, 1))
        )
        text = format_breakdown(r)
        assert "AdFee" in text
        # 列顺序:Fee 在 AdFee 前面,AdFee 在 Profit 前面
        fee_pos = text.find("Fee ")
        adfee_pos = text.find("AdFee")
        profit_pos = text.find("Profit")
        assert 0 < fee_pos < adfee_pos < profit_pos
