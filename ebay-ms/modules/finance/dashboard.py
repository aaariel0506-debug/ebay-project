"""Finance Dashboard — 只读聚合服务, JPY 本位.

⚠️ 数据完整性警告:
 当前 Transaction.FEE 只包含平台费 + 国际费 + (部分)广告费。
 未采集:sales_tax / shipping_actual / ad_fee(可能部分漏采)。
 详见 docs/finance-semantics.md, Day 31 扩采集。
 因此本看板 gross_profit 系统性偏高。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from core.models import Order, OrderItem, Product, Transaction, TransactionType
from sqlalchemy import case, func
from sqlalchemy.orm import Session

UNCAPTURED_ITEMS: tuple[str, ...] = (
    "sales_tax",
    "shipping_actual",
    "ad_fee_possibly_partial",
)


@dataclass
class DateRange:
    start: datetime | None = None
    end: datetime | None = None


@dataclass
class SkuProfitRow:
    sku: str
    title: str | None
    units_sold: int
    revenue_jpy: Decimal
    cost_jpy: Decimal
    profit_jpy: Decimal
    margin: float | None


@dataclass
class DashboardResult:
    date_range: DateRange
    total_revenue_jpy: Decimal
    total_cost_jpy: Decimal
    total_fee_jpy: Decimal
    gross_profit_jpy: Decimal
    gross_margin: float | None
    total_orders: int
    avg_order_value_jpy: Decimal | None
    avg_order_margin: float | None
    total_transactions: int
    uncovered_transactions: int
    coverage_ratio: float
    uncaptured_items: tuple[str, ...] = UNCAPTURED_ITEMS
    top_profit_skus: list[SkuProfitRow] = field(default_factory=list)
    top_loss_skus: list[SkuProfitRow] = field(default_factory=list)
    top_units_skus: list[SkuProfitRow] = field(default_factory=list)


class DashboardService:
    def __init__(self, session: Session):
        self._sess = session

    @staticmethod
    def this_month() -> DateRange:
        now = datetime.now()
        start = datetime(now.year, now.month, 1)
        end = datetime(now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1)
        return DateRange(start=start, end=end)

    @staticmethod
    def this_week() -> DateRange:
        now = datetime.now()
        start = datetime(now.year, now.month, now.day) - timedelta(days=now.weekday())
        end = start + timedelta(days=7)
        return DateRange(start=start, end=end)

    @staticmethod
    def last_n_days(n: int) -> DateRange:
        end = datetime.now() + timedelta(days=1)
        start = end - timedelta(days=n)
        return DateRange(start=start, end=end)

    def compute(self, *, date_range: DateRange | None = None) -> DashboardResult:
        date_range = date_range or DateRange()
        tx_query = self._sess.query(Transaction)
        order_query = self._sess.query(Order)
        item_query = self._sess.query(OrderItem)

        if date_range.start is not None:
            tx_query = tx_query.filter(Transaction.date >= date_range.start)
            order_query = order_query.filter(Order.order_date >= date_range.start)
            item_query = item_query.join(Order, OrderItem.order_id == Order.ebay_order_id).filter(Order.order_date >= date_range.start)
        if date_range.end is not None:
            tx_query = tx_query.filter(Transaction.date < date_range.end)
            order_query = order_query.filter(Order.order_date < date_range.end)
            item_query = item_query.join(Order, OrderItem.order_id == Order.ebay_order_id) if date_range.start is None else item_query
            item_query = item_query.filter(Order.order_date < date_range.end)

        metrics = tx_query.with_entities(
            func.count(Transaction.id),
            func.sum(case((Transaction.type.in_([TransactionType.SALE, TransactionType.SHIPPING, TransactionType.REFUND]), Transaction.amount_jpy), else_=Decimal("0"))),
            func.sum(case((Transaction.type == TransactionType.SALE, Transaction.total_cost), else_=Decimal("0"))),
            func.sum(case((Transaction.type == TransactionType.FEE, func.abs(Transaction.amount_jpy)), else_=Decimal("0"))),
            func.sum(case((Transaction.amount_jpy.is_(None), 1), else_=0)),
        ).one()

        total_transactions = int(metrics[0] or 0)
        total_revenue = Decimal(str(metrics[1] or 0))
        total_cost = Decimal(str(metrics[2] or 0))
        total_fee = Decimal(str(metrics[3] or 0))
        uncovered = int(metrics[4] or 0)
        gross_profit = total_revenue - total_cost - total_fee
        gross_margin = float(gross_profit / total_revenue) if total_revenue > 0 else None
        coverage_ratio = (total_transactions - uncovered) / total_transactions if total_transactions > 0 else 1.0

        total_orders = order_query.count()
        avg_order_value = (total_revenue / Decimal(str(total_orders))) if total_orders > 0 else None
        avg_order_margin = self._compute_avg_order_margin(date_range)

        top_rows = self._compute_sku_rows(date_range)
        top_profit = sorted([r for r in top_rows if r.profit_jpy > 0], key=lambda r: r.profit_jpy, reverse=True)[:10]
        top_loss = sorted([r for r in top_rows if r.profit_jpy < 0], key=lambda r: r.profit_jpy)[:10]
        top_units = sorted(top_rows, key=lambda r: r.units_sold, reverse=True)[:10]

        return DashboardResult(
            date_range=date_range,
            total_revenue_jpy=total_revenue,
            total_cost_jpy=total_cost,
            total_fee_jpy=total_fee,
            gross_profit_jpy=gross_profit,
            gross_margin=gross_margin,
            total_orders=total_orders,
            avg_order_value_jpy=avg_order_value,
            avg_order_margin=avg_order_margin,
            total_transactions=total_transactions,
            uncovered_transactions=uncovered,
            coverage_ratio=coverage_ratio,
            top_profit_skus=top_profit,
            top_loss_skus=top_loss,
            top_units_skus=top_units,
        )

    def _compute_avg_order_margin(self, date_range: DateRange) -> float | None:
        order_ids_query = self._sess.query(Order.ebay_order_id)
        if date_range.start is not None:
            order_ids_query = order_ids_query.filter(Order.order_date >= date_range.start)
        if date_range.end is not None:
            order_ids_query = order_ids_query.filter(Order.order_date < date_range.end)
        order_ids = [row[0] for row in order_ids_query.all()]
        margins: list[Decimal] = []
        for order_id in order_ids:
            txs = self._sess.query(Transaction).filter(Transaction.order_id == order_id).all()
            order_revenue = Decimal("0")
            order_cost = Decimal("0")
            order_fee = Decimal("0")
            for tx in txs:
                amount_jpy = Decimal(str(tx.amount_jpy)) if tx.amount_jpy is not None else None
                if tx.type in (TransactionType.SALE, TransactionType.SHIPPING, TransactionType.REFUND) and amount_jpy is not None:
                    order_revenue += amount_jpy
                if tx.type == TransactionType.SALE and tx.total_cost is not None:
                    order_cost += Decimal(str(tx.total_cost))
                if tx.type == TransactionType.FEE and amount_jpy is not None:
                    order_fee += abs(amount_jpy)
            if order_revenue > 0:
                margins.append((order_revenue - order_cost - order_fee) / order_revenue)
        if not margins:
            return None
        return float(sum(margins, Decimal("0")) / Decimal(str(len(margins))))

    def _compute_sku_rows(self, date_range: DateRange) -> list[SkuProfitRow]:
        query = (
            self._sess.query(
                Transaction.sku,
                Product.title,
                func.sum(OrderItem.quantity),
                func.sum(Transaction.amount_jpy),
                func.sum(Transaction.total_cost),
            )
            .join(OrderItem, (OrderItem.order_id == Transaction.order_id) & (OrderItem.sku == Transaction.sku))
            .outerjoin(Product, Product.sku == Transaction.sku)
            .filter(Transaction.type == TransactionType.SALE)
            .filter(Transaction.amount_jpy.is_not(None))
        )
        if date_range.start is not None:
            query = query.filter(Transaction.date >= date_range.start)
        if date_range.end is not None:
            query = query.filter(Transaction.date < date_range.end)
        query = query.group_by(Transaction.sku, Product.title)

        rows: list[SkuProfitRow] = []
        for sku, title, units_sold, revenue_jpy, cost_jpy in query.all():
            revenue = Decimal(str(revenue_jpy or 0))
            cost = Decimal(str(cost_jpy or 0))
            profit = revenue - cost
            margin = float(profit / revenue) if revenue > 0 else None
            rows.append(
                SkuProfitRow(
                    sku=sku,
                    title=title,
                    units_sold=int(units_sold or 0),
                    revenue_jpy=revenue,
                    cost_jpy=cost,
                    profit_jpy=profit,
                    margin=margin,
                )
            )
        return rows


def _fmt_yen(amount: Decimal | None) -> str:
    if amount is None:
        return "N/A"
    return f"¥{int(amount):,}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def format_dashboard(result: DashboardResult) -> str:
    start = result.date_range.start.date().isoformat() if result.date_range.start else "all"
    end = result.date_range.end.date().isoformat() if result.date_range.end else "all"
    lines = [
        "╔═══ Finance Dashboard ═══════════════════════════════════════╗",
        f"║ 时间范围 : {start} ~ {end}",
        "║",
        f"║ 总收入 : {_fmt_yen(result.total_revenue_jpy)}",
        f"║ 总成本 : {_fmt_yen(result.total_cost_jpy)}",
        f"║ 总手续费 : {_fmt_yen(result.total_fee_jpy)}",
        f"║ 毛利润 : {_fmt_yen(result.gross_profit_jpy)}",
        f"║ 毛利率 : {_fmt_pct(result.gross_margin)}",
        "║",
        f"║ 订单数 : {result.total_orders}",
        f"║ 平均客单价: {_fmt_yen(result.avg_order_value_jpy)}",
        f"║ 平均利润率: {_fmt_pct(result.avg_order_margin)} (订单级平均,非 sum-based)",
        "║",
        "║ ⚠️ 未采集项(当前毛利润系统性偏高):",
    ]
    for item in result.uncaptured_items:
        lines.append(f"║ - {item}")
    lines.extend(
        [
            "║ 详见 docs/finance-semantics.md,Day 31 补齐",
            "║",
            f"║ 流水覆盖 : {result.total_transactions - result.uncovered_transactions} / {result.total_transactions} 条 ({result.coverage_ratio * 100:.2f}%)",
            f"║ 未覆盖 {result.uncovered_transactions} 条(汇率缺失),不计入上述金额",
            "╠═══ Top 10 利润 SKU ═════════════════════════════════════════╣",
        ]
    )
    if result.top_profit_skus:
        for idx, row in enumerate(result.top_profit_skus, start=1):
            lines.append(f"║ {idx}. {row.sku} ({row.title or '-'}) {row.units_sold} 件 {_fmt_yen(row.profit_jpy)} {_fmt_pct(row.margin)}")
    else:
        lines.append("║ (无利润 SKU)")
    lines.append("╠═══ Top 10 亏损 SKU ═════════════════════════════════════════╣")
    if result.top_loss_skus:
        for idx, row in enumerate(result.top_loss_skus, start=1):
            lines.append(f"║ {idx}. {row.sku} ({row.title or '-'}) {row.units_sold} 件 {_fmt_yen(row.profit_jpy)} {_fmt_pct(row.margin)}")
    else:
        lines.append("║ (无亏损 SKU)")
    lines.append("╠═══ Top 10 销量 SKU ═════════════════════════════════════════╣")
    if result.top_units_skus:
        for idx, row in enumerate(result.top_units_skus, start=1):
            lines.append(f"║ {idx}. {row.sku} ({row.title or '-'}) {row.units_sold} 件 {_fmt_yen(row.revenue_jpy)}")
    else:
        lines.append("║ (无销量 SKU)")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)
