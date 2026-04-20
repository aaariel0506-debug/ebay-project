"""
modules/finance/order_sync_service.py

Day 26: eBay 订单拉取服务

功能：
- 从 eBay Fulfillment API 拉取已完成订单（GET /sell/fulfillment/v1/order）
- 增量同步（按日期范围）
- 解析 Fee（从 order.lineItems.itemTx Summaries 或 Finances API）
- 写入 Order 表（upsert）
- 写入 Transaction 表（SALE / FEE / SHIPPING 流水）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from core.database.connection import get_session
from core.ebay_api.client import EbayClient
from core.models import Order, OrderStatus, Transaction, TransactionType
from loguru import logger as log

# ── 结果 ─────────────────────────────────────────────────────────────────

@dataclass
class OrderSyncResult:
    """订单同步结果。"""
    total_pages: int
    total_orders: int
    upserted: int
    skipped: int
    unlinked_skus: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"订单同步完成：共 {self.total_orders} 条 / "
            f"写入 {self.upserted} / 跳过 {self.skipped} / "
            f"未关联SKU {len(self.unlinked_skus)} 条 / "
            f"错误 {len(self.errors)} 条"
        )


# ── 解析辅助 ─────────────────────────────────────────────────────────────

def _decimal(val: Any) -> Decimal:
    """将 API 返回值转为 Decimal，失败返回 Decimal(0)。"""
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _parse_order_status(api_status: str | None) -> OrderStatus:
    """映射 eBay orderStatus → OrderStatus。"""
    if api_status is None:
        return OrderStatus.PENDING
    mapping = {
        "PAID": OrderStatus.PENDING,
        "IN_TRANSIT": OrderStatus.SHIPPED,
        "DELIVERED": OrderStatus.SHIPPED,
        "COMPLETED": OrderStatus.SHIPPED,
        "CANCELLED": OrderStatus.CANCELLED,
        "REFUNDED": OrderStatus.REFUNDED,
        "ACTIVE": OrderStatus.PENDING,
    }
    return mapping.get(api_status, OrderStatus.PENDING)


# ── Service ───────────────────────────────────────────────────────────────

class OrderSyncService:
    """
    eBay 订单同步服务。

    用法::

        svc = OrderSyncService()
        result = svc.sync_orders(
            date_from=datetime(2026, 1, 1),
            date_to=datetime(2026, 4, 20),
            page_size=100,
        )
        print(result.summary())
    """

    def __init__(self, client: EbayClient | None = None):
        self._client = client or EbayClient()

    # ── 公开 API ───────────────────────────────────────────────────────

    def sync_orders(
        self,
        date_from: datetime,
        date_to: datetime,
        page_size: int = 100,
    ) -> OrderSyncResult:
        """
        增量拉取指定日期范围的已完成订单。

        Args:
            date_from: 起始时间（含）
            date_to: 结束时间（含）
            page_size: 每页条数（eBay 上限 100）

        Returns:
            OrderSyncResult
        """
        date_from_iso = date_from.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        date_to_iso = date_to.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        params = {
            "orderDateRange.from": date_from_iso,
            "orderDateRange.to": date_to_iso,
            "orderStatus": "COMPLETED",
            "limit": str(page_size),
        }

        result = OrderSyncResult(
            total_pages=0,
            total_orders=0,
            upserted=0,
            skipped=0,
        )

        page_token: str | None = None
        first_page = True

        while first_page or page_token:
            first_page = False
            p = dict(params)
            if page_token:
                p["continuationToken"] = page_token

            log.info("拉取订单页（{}）...", p.get("continuationToken", "第1页"))
            resp = self._client.get("/sell/fulfillment/v1/order", params=p)

            orders: list[dict] = resp.get("orders", [])
            result.total_orders += len(orders)
            result.total_pages += 1

            for order_data in orders:
                try:
                    ok, unlinked_sku = self._upsert_order(order_data)
                    if not ok:
                        result.skipped += 1
                        if unlinked_sku:
                            result.unlinked_skus.append(unlinked_sku)
                    else:
                        result.upserted += 1
                except Exception as exc:
                    log.error("写入订单失败 [{}]: {}", order_data.get("orderId"), exc)
                    result.errors.append({
                        "order_id": order_data.get("orderId"),
                        "error": str(exc),
                    })

            # 下一页
            next_link = resp.get("next")
            if next_link:
                import urllib.parse as _up
                parsed = _up.urlparse(next_link)
                page_token = _up.parse_qs(parsed.query).get("continuation_token", [None])[0]
            else:
                page_token = None

        log.info(result.summary())
        return result

    # ── 内部：upsert ───────────────────────────────────────────────────

    def _upsert_order(self, data: dict) -> tuple[bool, str | None]:
        """
        将一条 eBay order 数据写入/更新 Order 表和 Transaction 表。

        Returns:
            (True, None) = upserted successfully
            (False, "sku") = skipped because SKU has no cost_price (unlinked)
            (False, None) = skipped because order has no lineItems or invalid data
        """
        order_id: str | None = data.get("orderId")
        if not order_id:
            return (False, None)

        # ── 基本字段解析 ───────────────────────────────────────────
        order_date_str = data.get("creationDate")
        order_date: datetime | None = None
        if order_date_str:
            try:
                order_date = datetime.fromisoformat(order_date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        line_items: list[dict] = data.get("lineItems", [])
        if not line_items:
            log.debug("订单 {} 无 lineItems，跳过", order_id)
            return (False, None)

        # ── 逐 SKU 写入 Order（支持多 SKU 订单）────────────────────
        unlinked_skus_in_order: list[str] = []

        with get_session() as sess:
            for li in line_items:
                sku = li.get("sku")
                if not sku:
                    continue

                quantity = int(li.get("quantity", 0) or 0)
                unit_price = _decimal(li.get("lineItemCost", {}).get("value", 0))
                sale_amount = unit_price * quantity

                # 运费
                shipping_cost = _decimal(
                    data.get("fulfillmentHrefs", [{}])[0].get("shippingCost", {})
                    .get("value", 0) if data.get("fulfillmentHrefs") else 0
                )
                # eBay fee（从 order 层的 fee 汇总，或从 Finances API 补全）
                total_fee = self._extract_fee_from_order(data, order_id)

                # buyer info
                shipping_address = data.get("shippingAddress", {}) or {}
                buyer_country = shipping_address.get("country") or data.get("buyerCountry")

                # order status
                api_status = data.get("orderFulfillmentStatus", {}).get("status")
                status = _parse_order_status(api_status)

                # ── upsert Order ─────────────────────────────────
                existing = sess.query(Order).filter(Order.ebay_order_id == order_id).first()

                if existing:
                    # 更新字段（Order 不变性低，以最新状态为准）
                    existing.sale_price = sale_amount
                    existing.shipping_cost = shipping_cost
                    existing.ebay_fee = total_fee
                    existing.status = status
                    if order_date:
                        existing.order_date = order_date
                else:
                    new_order = Order(
                        ebay_order_id=order_id,
                        sku=sku,
                        sale_price=sale_amount,
                        shipping_cost=shipping_cost,
                        ebay_fee=total_fee,
                        buyer_country=buyer_country,
                        status=status,
                        order_date=order_date,
                        buyer_name=shipping_address.get("recipient", ""),
                        shipping_address=str(shipping_address)[:500],
                    )
                    sess.add(new_order)

                sess.flush()

                # ── Transaction 流水 ─────────────────────────────
                # 获取 Product 当前进货价（简化成本，非 FIFO）
                from core.models import Product
                product_row = sess.query(Product).filter(Product.sku == sku).first()
                product_cost: Decimal | None = product_row.cost_price if product_row else None

                if product_cost is None:
                    unlinked_skus_in_order.append(sku)

                self._write_transactions(
                    sess,
                    order_id=order_id,
                    sku=sku,
                    quantity=quantity,
                    sale_amount=sale_amount,
                    shipping_cost=shipping_cost,
                    fee_amount=total_fee,
                    order_date=order_date,
                    currency="USD",
                    unit_cost=product_cost,
                )

            sess.commit()

        # 若所有 SKU 都 unlinked → 视为 unlinked 订单（跳过）
        # 若部分 unlinked → 仍写入，仅报告这些 SKU
        if unlinked_skus_in_order and len(unlinked_skus_in_order) == len([li for li in line_items if li.get("sku")]):
            return (False, unlinked_skus_in_order[0])
        elif unlinked_skus_in_order:
            return (True, None)  # 部分关联，部分未关联，返回成功但不标记为跳过
        return (True, None)

    def _write_transactions(
        self,
        sess,
        order_id: str,
        sku: str,
        quantity: int,
        sale_amount: Decimal,
        shipping_cost: Decimal,
        fee_amount: Decimal,
        order_date: datetime | None,
        currency: str,
        unit_cost: Decimal | None = None,
    ):
        """
        为一笔 Order 写入 Transaction 流水（Sale + Fee + Shipping）。

        幂等性：每种 TransactionType 独立去重检查，
        避免同一 (order_id, sku) 下 SALE 存在后 BLOCK FEE/SHIPPING 写入。
        """

        # ── 成本和利润计算（SALE 专用）────────────────────
        total_cost_val: float | None = None
        profit_val: float | None = None
        margin_val: float | None = None

        if sale_amount > 0 and unit_cost is not None:
            total_cost_val = float(unit_cost * quantity)
            profit_val = float(sale_amount) - total_cost_val
            sale_f = float(sale_amount)
            if sale_f > 0:
                margin_val = profit_val / sale_f

        # SALE
        if sale_amount > 0:
            has_sale = sess.query(Transaction).filter(
                Transaction.order_id == order_id,
                Transaction.sku == sku,
                Transaction.type == TransactionType.SALE,
            ).first()
            if not has_sale:
                sess.add(Transaction(
                    order_id=order_id,
                    sku=sku,
                    type=TransactionType.SALE,
                    amount=float(sale_amount),
                    currency=currency,
                    date=order_date,
                    unit_cost=float(unit_cost) if unit_cost is not None else None,
                    total_cost=total_cost_val,
                    profit=profit_val,
                    margin=margin_val,
                ))

        # SHIPPING
        if shipping_cost > 0:
            has_shipping = sess.query(Transaction).filter(
                Transaction.order_id == order_id,
                Transaction.sku == sku,
                Transaction.type == TransactionType.SHIPPING,
            ).first()
            if not has_shipping:
                sess.add(Transaction(
                    order_id=order_id,
                    sku=sku,
                    type=TransactionType.SHIPPING,
                    amount=float(shipping_cost),
                    currency=currency,
                    date=order_date,
                ))

        # FEE（eBay fee，负数）
        if fee_amount > 0:
            has_fee = sess.query(Transaction).filter(
                Transaction.order_id == order_id,
                Transaction.sku == sku,
                Transaction.type == TransactionType.FEE,
            ).first()
            if not has_fee:
                sess.add(Transaction(
                    order_id=order_id,
                    sku=sku,
                    type=TransactionType.FEE,
                    amount=float(-fee_amount),
                    currency=currency,
                    date=order_date,
                ))

    def _extract_fee_from_order(self, data: dict, order_id: str) -> Decimal:
        """
        从 order 响应中提取 eBay fee。

        eBay Fulfillment API 的 order 响应中，
        lineItems 含有 itemTxSummaries（费用明细）。
        如果没有，尝试从 /sell/finances/v1/transactions 补全（TODO）。
        """
        total_fee = Decimal("0")
        for li in data.get("lineItems", []):
            for summary in li.get("itemTxSummaries", []):
                if summary.get("transactionType") == "FEE":
                    total_fee += _decimal(summary.get("amount", {}).get("value", 0))
        if total_fee > 0:
            return total_fee

        # 备用：尝试从 orderId 查 Finances API
        try:
            resp = self._client.get(
                "/sell/finances/v1/transactions",
                params={"orderId": order_id, "transactionType": "FEE"},
            )
            for txn in resp.get("transactions", []):
                total_fee += _decimal(txn.get("amount", {}).get("value", 0))
        except Exception as exc:
            log.debug(" Finances API 查询失败 [{}]: {}", order_id, exc)

        return total_fee
