from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from core.models import Transaction
from modules.finance.dashboard import (
    UNCAPTURED_ITEMS,
    DashboardService,
    DateRange,
    _fmt_pct,
    _fmt_yen,
)
from sqlalchemy import func
from sqlalchemy.orm import Session


@dataclass
class BreakdownRow:
    period: str
    period_start: datetime
    period_end: datetime
    revenue_jpy: Decimal
    cost_jpy: Decimal
    fee_jpy: Decimal
    ad_fee_jpy: Decimal
    gross_profit_jpy: Decimal
    gross_margin: float | None
    total_orders: int
    total_transactions: int
    uncovered_transactions: int
    coverage_ratio: float


@dataclass
class BreakdownResult:
    group_by: str
    date_range: DateRange
    rows: list[BreakdownRow]
    uncaptured_items: tuple[str, ...] = UNCAPTURED_ITEMS


class BreakdownService:
    def __init__(self, session: Session):
        self._sess = session

    def compute(self, *, group_by: str, date_range: DateRange) -> BreakdownResult:
        if group_by not in {"month", "day"}:
            raise ValueError(f"invalid group_by: {group_by}")
        if date_range.start is None or date_range.end is None:
            raise ValueError("date_range.start and date_range.end are required")
        rows: list[BreakdownRow] = []
        iterator = _iter_month_buckets if group_by == "month" else _iter_day_buckets
        dashboard_service = DashboardService(self._sess)
        for bucket_start, bucket_end in iterator(date_range.start, date_range.end):
            dash = dashboard_service.compute(
                date_range=DateRange(start=bucket_start, end=bucket_end),
                include_sku_analysis=False,
                include_order_margin=False,
            )
            if dash.total_transactions == 0:
                continue
            rows.append(
                BreakdownRow(
                    period=bucket_start.strftime("%Y-%m" if group_by == "month" else "%Y-%m-%d"),
                    period_start=bucket_start,
                    period_end=bucket_end,
                    revenue_jpy=dash.total_revenue_jpy,
                    cost_jpy=dash.total_cost_jpy,
                    fee_jpy=dash.total_fee_jpy,
                    ad_fee_jpy=dash.total_ad_fee_jpy,
                    gross_profit_jpy=dash.gross_profit_jpy,
                    gross_margin=dash.gross_margin,
                    total_orders=dash.total_orders,
                    total_transactions=dash.total_transactions,
                    uncovered_transactions=dash.uncovered_transactions,
                    coverage_ratio=dash.coverage_ratio,
                )
            )
        return BreakdownResult(group_by=group_by, date_range=date_range, rows=rows)


def _iter_month_buckets(start: datetime, end: datetime):
    cur = datetime(start.year, start.month, 1)
    while cur < end:
        if cur.month == 12:
            nxt = datetime(cur.year + 1, 1, 1)
        else:
            nxt = datetime(cur.year, cur.month + 1, 1)
        yield cur, nxt
        cur = nxt


def _iter_day_buckets(start: datetime, end: datetime):
    cur = datetime(start.year, start.month, start.day)
    while cur < end:
        nxt = cur + timedelta(days=1)
        yield cur, nxt
        cur = nxt


def resolve_all_range(session: Session) -> DateRange:
    min_date, max_date = session.query(func.min(Transaction.date), func.max(Transaction.date)).one()
    if min_date is None or max_date is None:
        return DateRange(start=None, end=None)
    start = datetime(min_date.year, min_date.month, min_date.day)
    end = datetime(max_date.year, max_date.month, max_date.day) + timedelta(days=1)
    return DateRange(start=start, end=end)


def format_breakdown(result: BreakdownResult) -> str:
    start = result.date_range.start.date().isoformat() if result.date_range.start else "all"
    end = result.date_range.end.date().isoformat() if result.date_range.end else "all"
    lines = [
        f"╔═══ Finance Breakdown (by {result.group_by}) ═══════════════════════════════════╗",
        f"║ 时间范围 : {start} ~ {end}",
        "║",
    ]
    if not result.rows:
        lines.append("║ (无数据)")
    else:
        headers = ["Period", "Revenue", "Cost", "Fee", "AdFee", "Profit", "Margin", "Orders", "Cov"]
        rendered = [
            [
                row.period,
                _fmt_yen(row.revenue_jpy),
                _fmt_yen(row.cost_jpy),
                _fmt_yen(row.fee_jpy),
                _fmt_yen(row.ad_fee_jpy),
                _fmt_yen(row.gross_profit_jpy),
                _fmt_pct(row.gross_margin),
                str(row.total_orders),
                _fmt_pct(row.coverage_ratio),
            ]
            for row in result.rows
        ]
        widths = [len(h) for h in headers]
        for render_row in rendered:
            for idx, value in enumerate(render_row):
                widths[idx] = max(widths[idx], len(value))
        header_line = " ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        lines.append(f"║ {header_line}")
        for render_row in rendered:
            lines.append(f"║ {' '.join(value.ljust(widths[i]) for i, value in enumerate(render_row))}")
    lines.extend([
        "║",
        "║ ⚠️ 未采集项(当前毛利润仍偏高):",
    ])
    for item in result.uncaptured_items:
        if item == "shipping_actual":
            lines.append(f"║ - {item} (实际运费成本,Day 31.5 多源 CSV 导入后采集)")
        else:
            lines.append(f"║ - {item}")
    lines.append("║ 详见 docs/finance-semantics.md")
    lines.append("╚════════════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)
