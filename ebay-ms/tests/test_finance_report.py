"""tests/test_finance_report.py"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.models import Base, Transaction, TransactionType
from core.models.sync_meta import SyncMeta, get_last_sync, set_last_sync
from modules.finance.report import (
    TransactionReport,
    daily_report,
    monthly_report,
    weekly_report,
)


class TestTransactionReport:
    """TransactionReport 汇总功能测试。"""

    @pytest.fixture
    def sess(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        s = Session()
        yield s
        s.close()

    def _tx(self, sess, type_: TransactionType, amount: Decimal, date: datetime, **kw):
        t = Transaction(
            order_id=kw.get("order_id", "TEST-001"),
            type=type_,
            amount=amount,
            currency="USD",
            date=date,
            sku=kw.get("sku"),
            unit_cost=kw.get("unit_cost"),
            total_cost=kw.get("total_cost"),
            profit=kw.get("profit"),
            margin=kw.get("margin"),
        )
        sess.add(t)
        sess.commit()
        return t

    def test_summary_basic(self, sess):
        """汇总计算正确。"""
        now = datetime.now()
        self._tx(sess, TransactionType.SALE, Decimal("100.00"), now)
        self._tx(sess, TransactionType.FEE, Decimal("-8.00"), now)
        self._tx(sess, TransactionType.SHIPPING, Decimal("5.00"), now)

        rep = TransactionReport(sess)
        r = rep.summary(now - timedelta(hours=1), now + timedelta(hours=1))

        assert r["sales"] == Decimal("100.00")
        assert r["fees"] == Decimal("-8.00")
        assert r["shipping"] == Decimal("5.00")
        assert r["refund"] == Decimal("0")
        assert r["gross_profit"] == Decimal("97.00")
        assert r["margin"] == 0.97

    def test_summary_empty(self, sess):
        """无数据时返回零值。"""
        rep = TransactionReport(sess)
        r = rep.summary(datetime(2020, 1, 1), datetime(2020, 1, 2))
        assert r["sales"] == Decimal("0")
        assert r["gross_profit"] == Decimal("0")

    def test_summary_text(self, sess):
        """summary_text 输出可读。"""
        now = datetime.now()
        self._tx(sess, TransactionType.SALE, Decimal("100.00"), now)
        rep = TransactionReport(sess)
        text = rep.summary_text(now - timedelta(hours=1), now + timedelta(hours=1))
        assert "Transaction 汇总" in text
        assert "100.00" in text

    def test_daily_report(self, sess):
        """daily_report 返回今日汇总。"""
        today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        self._tx(sess, TransactionType.SALE, Decimal("200.00"), today)
        r = daily_report(sess)
        assert r["sales"] == Decimal("200.00")

    def test_weekly_report(self, sess):
        """weekly_report 返回本周汇总。"""
        today = datetime.now()
        self._tx(sess, TransactionType.SALE, Decimal("300.00"), today)
        r = weekly_report(sess)
        assert r["sales"] == Decimal("300.00")

    def test_monthly_report(self, sess):
        """monthly_report 返回指定月份汇总。"""
        today = datetime.now()
        self._tx(sess, TransactionType.SALE, Decimal("400.00"), today)
        r = monthly_report(sess, today.year, today.month)
        assert r["sales"] == Decimal("400.00")


class TestSyncMeta:
    """SyncMeta get/set 功能测试。"""

    @pytest.fixture
    def sess(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        s = Session()
        yield s
        s.close()

    def test_set_and_get(self, sess):
        """set_last_sync 后 get_last_sync 能读回。"""
        now = datetime.now()
        set_last_sync(sess, "finance", "sync_orders", now, "ORD-999")
        sess.commit()

        result = get_last_sync(sess, "finance", "sync_orders")
        assert result == now

    def test_get_nonexistent(self, sess):
        """不存在的记录返回 None。"""
        result = get_last_sync(sess, "none", "none")
        assert result is None

    def test_update_existing(self, sess):
        """已存在记录时覆盖。"""
        t1 = datetime(2026, 1, 1, 10, 0, 0)
        t2 = datetime(2026, 1, 2, 12, 0, 0)
        set_last_sync(sess, "finance", "sync_orders", t1)
        sess.commit()
        set_last_sync(sess, "finance", "sync_orders", t2, "ORD-002")
        sess.commit()

        assert get_last_sync(sess, "finance", "sync_orders") == t2

    def test_unique_constraint(self, sess):
        """同一 module+operation 只有一行。"""
        t = datetime.now()
        set_last_sync(sess, "finance", "sync_orders", t)
        sess.commit()
        set_last_sync(sess, "finance", "sync_orders", t + timedelta(hours=1))
        sess.commit()

        rows = sess.query(SyncMeta).filter(
            SyncMeta.module == "finance",
            SyncMeta.operation == "sync_orders",
        ).all()
        assert len(rows) == 1
