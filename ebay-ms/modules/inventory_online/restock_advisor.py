"""
modules/inventory_online/restock_advisor.py

Day 17: 自动补货建议

功能：
- 基于历史销售速度计算预计售罄天数
- 生成补货建议清单（urgent / soon / normal）
- 支持批量补货建议导出
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# 默认阈值
DEFAULT_URGENT_DAYS = 7
DEFAULT_SOON_DAYS = 14
DEFAULT_TARGET_DAYS = 30        # 希望维持多少天库存
DEFAULT_MIN_SALES_FOR_ANALYSIS = 2  # 最少需要 N 笔订单才计算速度


@dataclass
class RestockItem:
    """单个 SKU 的补货建议。"""
    sku: str
    title: str | None
    current_quantity: int
    avg_daily_sales: float       # 平均每日销量
    days_until_stockout: float   # 预计售罄天数
    urgency: str                 # urgent / soon / normal
    suggested_quantity: int      # 建议补货数量
    estimated_cost: float | None  # 预估补货成本（JPY）
    last_order_date: date | None # 最近一笔订单日期


class RestockAdvisor:
    """补货建议服务。"""

    def __init__(
        self,
        urgent_days: int = DEFAULT_URGENT_DAYS,
        soon_days: int = DEFAULT_SOON_DAYS,
        target_days: int = DEFAULT_TARGET_DAYS,
        min_sales: int = DEFAULT_MIN_SALES_FOR_ANALYSIS,
    ):
        self.urgent_days = urgent_days
        self.soon_days = soon_days
        self.target_days = target_days
        self.min_sales = min_sales

    def get_restock_list(self, lookback_days: int = 30) -> list[RestockItem]:
        """
        计算所有活跃 SKU 的补货建议。

        Args:
            lookback_days: 分析近 N 天的销售数据

        Returns:
            list[RestockItem]：按 urgency 排序（urgent → soon → normal）
        """
        from core.database.connection import get_session
        from core.models import EbayListing, Order, OrderStatus, Product

        with get_session() as sess:
            cutoff_date = date.today() - timedelta(days=lookback_days)

            # 拉取所有活跃 listing
            listings = (
                sess.query(EbayListing, Product)
                .join(Product, EbayListing.sku == Product.sku)
                .filter(EbayListing.status.name == "ACTIVE")
                .all()
            )

            results: list[RestockItem] = []

            for listing, product in listings:
                sku = listing.sku
                current_qty = listing.quantity_available or 0

                # 查近 N 天订单数
                orders = (
                    sess.query(Order)
                    .filter(
                        Order.sku == sku,
                        Order.status == OrderStatus.SHIPPED,
                        Order.order_date.isnot(None),
                        Order.order_date >= cutoff_date,
                    )
                    .all()
                )

                recent_orders = [o for o in orders if o.order_date]

                if len(recent_orders) < self.min_sales:
                    # 销售数据不足，跳过速度计算
                    avg_sales = 0.0
                    days_until = 999.0
                    urgency = "unknown"
                    suggested_qty = 0
                else:
                    avg_daily = len(recent_orders) / lookback_days
                    avg_sales = round(avg_daily, 2)

                    if avg_sales > 0:
                        days_until = current_qty / avg_sales
                    else:
                        days_until = 999.0

                    if days_until <= self.urgent_days:
                        urgency = "urgent"
                    elif days_until <= self.soon_days:
                        urgency = "soon"
                    else:
                        urgency = "normal"

                    # 建议补货量 = 目标库存 - 当前库存
                    # 目标库存 = avg_daily * target_days
                    target_qty = max(int(avg_sales * self.target_days), 1)
                    suggested_qty = max(target_qty - current_qty, 0)

                # 预估成本
                estimated_cost = None
                if suggested_qty > 0 and product.cost_price:
                    estimated_cost = float(product.cost_price) * suggested_qty

                # 最近订单日期
                last_order_date = None
                if recent_orders:
                    order_dates = [
                        o.order_date.date()
                        for o in recent_orders
                        if o.order_date
                    ]
                    if order_dates:
                        last_order_date = max(order_dates)

                results.append(RestockItem(
                    sku=sku,
                    title=product.title,
                    current_quantity=current_qty,
                    avg_daily_sales=avg_sales,
                    days_until_stockout=round(days_until, 1),
                    urgency=urgency,
                    suggested_quantity=suggested_qty,
                    estimated_cost=estimated_cost,
                    last_order_date=last_order_date,
                ))

            # 按 urgency 排序
            urgency_order = {"urgent": 0, "soon": 1, "normal": 2, "unknown": 3}
            results.sort(key=lambda x: urgency_order.get(x.urgency, 4))

            return results

    def print_report(self, lookback_days: int = 30) -> None:
        """打印补货建议报告。"""
        items = self.get_restock_list(lookback_days)

        if not items:
            print("无活跃商品或销售数据")
            return

        urgent = [i for i in items if i.urgency == "urgent"]
        soon = [i for i in items if i.urgency == "soon"]
        normal = [i for i in items if i.urgency == "normal"]
        unknown = [i for i in items if i.urgency == "unknown"]

        print(f"\n{'='*70}")
        print(f"补货建议报告（近 {lookback_days} 天销售数据）")
        print(f"{'='*70}")

        for label, group in [("🚨 紧急补货（< 7 天）", urgent),
                              ("⚠️  近期补货（< 14 天）", soon),
                              ("✅ 正常库存", normal),
                              ("❓ 数据不足", unknown)]:
            if not group:
                continue
            print(f"\n{label}：{len(group)} 件")
            print(f"{'SKU':<20} {'当前库存':>8} {'日均销量':>8} {'售罄天数':>8} {'建议补货':>8} {'预估成本':>10}")
            print("-" * 70)
            for item in group:
                cost_str = f"¥{item.estimated_cost:,.0f}" if item.estimated_cost else "-"
                print(
                    f"{item.sku:<20} "
                    f"{item.current_quantity:>8} "
                    f"{item.avg_daily_sales:>8.2f} "
                    f"{item.days_until_stockout:>8.1f} "
                    f"{item.suggested_quantity:>8} "
                    f"{cost_str:>10}"
                )

        print(f"\n汇总：紧急 {len(urgent)} | 近期 {len(soon)} | 正常 {len(normal)} | 数据不足 {len(unknown)}")
