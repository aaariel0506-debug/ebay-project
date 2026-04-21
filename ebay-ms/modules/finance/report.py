"""finance/report.py — Transaction 汇总报告"""
from datetime import datetime
from decimal import Decimal

from core.models import Transaction, TransactionType
from sqlalchemy import func
from sqlalchemy.orm import Session


class TransactionReport:
    """Transaction 汇总报告生成器。"""

    def __init__(self, sess: Session):
        self.sess = sess

    def summary(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> dict:
        """
        汇总指定日期范围内的 Transaction 流水。

        Returns:
            {
                "sales": Decimal,
                "fees": Decimal,       # 负数（平台费）
                "shipping": Decimal,
                "gross_profit": Decimal,
                "margin": float,      # gross_profit / sales
                "tx_count": int,
            }
        """
        rows = self.sess.query(
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        ).filter(
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        ).group_by(
            Transaction.type
        ).all()

        totals: dict[str, tuple[float, int]] = {t.value: (0.0, 0) for t in TransactionType}
        for row in rows:
            totals[row.type.value] = (float(row.total or 0), row.count or 0)

        sales = Decimal(str(totals["sale"][0]))
        fees = Decimal(str(totals["fee"][0]))  # 负数
        shipping = Decimal(str(totals["shipping"][0]))
        refund = Decimal(str(totals["refund"][0]))
        gross_profit = sales + fees + shipping + refund  # fees 为负所以是加
        margin = float(gross_profit / sales) if sales else 0.0
        tx_count = sum(c for _, c in totals.values())

        return {
            "sales": sales,
            "fees": fees,
            "shipping": shipping,
            "refund": refund,
            "gross_profit": gross_profit,
            "margin": margin,
            "tx_count": tx_count,
            "date_from": date_from,
            "date_to": date_to,
        }

    def summary_text(self, date_from: datetime, date_to: datetime) -> str:
        r = self.summary(date_from, date_to)
        lines = [
            f"Transaction 汇总  {date_from.strftime('%Y-%m-%d')} ~ {date_to.strftime('%Y-%m-%d')}",
            f"  销售额（Sales）    : ${r['sales']:.2f}",
            f"  平台费（Fees）     : ${r['fees']:.2f}",
            f"  运费（Shipping）   : ${r['shipping']:.2f}",
            f"  退款（Refunds）    : ${r['refund']:.2f}",
            "  ─────────────────────────────────",
            f"  毛利（Gross Profit）: ${r['gross_profit']:.2f}",
            f"  利润率（Margin）   : {r['margin']*100:.1f}%",
            f"  流水笔数（Tx Count）: {r['tx_count']}",
        ]
        return "\n".join(lines)


def daily_report(sess: Session, target_date: datetime | None = None) -> dict:
    """返回指定日期（或今天）的汇总。"""
    if target_date is None:
        target_date = datetime.now()
    from datetime import timedelta
    start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    reporter = TransactionReport(sess)
    return reporter.summary(start, end)


def weekly_report(sess: Session, target_date: datetime | None = None) -> dict:
    """返回本周汇总（周一到周日）。"""
    if target_date is None:
        target_date = datetime.now()
    from datetime import timedelta
    weekday = target_date.weekday()  # 0=Mon
    start = (target_date - timedelta(days=weekday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    reporter = TransactionReport(sess)
    return reporter.summary(start, end)


def monthly_report(sess: Session, year: int, month: int) -> dict:
    """返回指定年月的月汇总。"""
    from datetime import datetime as dt
    start = dt(year, month, 1)
    if month == 12:
        end = dt(year + 1, 1, 1)
    else:
        end = dt(year, month + 1, 1)
    reporter = TransactionReport(sess)
    return reporter.summary(start, end)
