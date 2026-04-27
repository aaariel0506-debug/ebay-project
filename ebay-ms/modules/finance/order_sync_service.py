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
from core.models import Order, OrderItem, OrderStatus, Transaction, TransactionType
from core.utils.currency import RateNotFoundError, convert
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

        支持多 SKU 订单：每个 lineItem 对应一条 OrderItem 行。

        Returns:
            (True, None) = upserted successfully
            (False, "sku") = skipped because ALL SKUs have no cost_price (unlinked)
            (False, None) = skipped because order has no lineItems or invalid data
        """
        order_id: str | None = data.get("orderId")
        if not order_id:
            return (False, None)

        # ── 基本字段解析（订单级，一次）──────────────────────────────
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

        # buyer info（订单级）
        shipping_address = data.get("shippingAddress", {}) or {}
        buyer_country = shipping_address.get("country") or data.get("buyerCountry")

        # buyer_paid_total 在后面通过 _extract_buyer_paid_total 计算
        # （此处不单独读取 pricingSummary.total）

        # order status
        api_status = data.get("orderFulfillmentStatus", {}).get("status")
        status = _parse_order_status(api_status)

        # shipping cost（订单级，从 pricingSummary.deliveryCost 读）
        # 注：Day 25-27 的代码写 fulfillmentHrefs，但真实响应 fulfillmentHrefs 经常为空数组，
        # 而 pricingSummary.deliveryCost 是订单级的稳定字段。
        shipping_cost = _decimal(
            data.get("pricingSummary", {}).get("deliveryCost", {}).get("value", 0)
        )

        # fee（订单级）— Day 31-B: 一次 Finances API 调用，缓存供 FEE/AD_FEE/SALE_TAX 共用
        transactions = self._fetch_finances_transactions(order_id)
        total_fee = self._extract_fee_from_transactions(data, order_id, transactions)
        total_ad_fee = self._extract_ad_fee_from_transactions(order_id, transactions)
        total_sale_tax = self._extract_sale_tax_from_transactions(order_id, transactions)

        # buyer_paid_total：pricingSummary.total + taxes（Day 31-B 启用）
        buyer_paid_total = self._extract_buyer_paid_total(data)

        # tracking_no：从 shipping_fulfillment 子资源采集（Day 31.5-A）
        tracking_no = self._fetch_tracking_no(order_id)

        # ── 计算各 lineItem 的明细 ──────────────────────────────────
        li_data: list[dict] = []
        unlinked_skus: list[str] = []
        with get_session() as sess:
            for li in line_items:
                sku = li.get("sku")
                if not sku:
                    continue
                quantity = int(li.get("quantity", 0) or 0)
                unit_price = _decimal(li.get("lineItemCost", {}).get("value", 0))
                sale_amount = unit_price * quantity

                # 获取 Product 当前进货价
                from core.models import Product
                product_row = sess.query(Product).filter(Product.sku == sku).first()
                product_cost: Decimal | None = (
                    product_row.cost_price if product_row else None
                )
                if product_cost is None:
                    unlinked_skus.append(sku)

                li_data.append({
                    "sku": sku,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "sale_amount": sale_amount,
                    "product_cost": product_cost,
                })

            if not li_data:
                return (False, None)

            # ── Order 总额 = sum(OrderItem.sale_amount) ─────────────
            total_sale_price = sum(d["sale_amount"] for d in li_data)

            # ── upsert Order（订单级字段，无 sku）──────────────────
            existing_order = (
                sess.query(Order)
                .filter(Order.ebay_order_id == order_id)
                .first()
            )
            if existing_order:
                existing_order.sale_price = float(total_sale_price)
                existing_order.shipping_cost = float(shipping_cost)
                existing_order.ebay_fee = float(total_fee)
                existing_order.status = status
                existing_order.buyer_country = buyer_country
                if order_date:
                    existing_order.order_date = order_date
                if buyer_paid_total:
                    existing_order.buyer_paid_total = float(buyer_paid_total)
                # Day 28.5 新字段：total_due_seller_raw + sold_via_ad_campaign
                total_due_seller_val = _decimal(
                    data.get("paymentSummary", {}).get("totalDueSeller", {}).get("value", 0)
                )
                sold_via_ad = data.get("properties", {}).get("soldViaAdCampaign", False)
                existing_order.total_due_seller_raw = float(total_due_seller_val) if total_due_seller_val > 0 else None
                existing_order.sold_via_ad_campaign = bool(sold_via_ad)
                # Day 31-B: AD_FEE 合计写入 Order
                if total_ad_fee > 0:
                    existing_order.ad_fee_total = float(total_ad_fee)
                # Day 31.5-A: tracking_no 从 shipping_fulfillment 子资源采集
                if tracking_no is not None:
                    existing_order.tracking_no = tracking_no
            else:
                new_order = Order(
                    ebay_order_id=order_id,
                    sale_price=float(total_sale_price),
                    shipping_cost=float(shipping_cost),
                    ebay_fee=float(total_fee),
                    buyer_country=buyer_country,
                    status=status,
                    order_date=order_date,
                    buyer_name=shipping_address.get("recipient", ""),
                    shipping_address=str(shipping_address)[:500],
                    buyer_paid_total=float(buyer_paid_total) if buyer_paid_total else None,
                    # Day 28.5 新字段：total_due_seller_raw + sold_via_ad_campaign
                    total_due_seller_raw=(
                        float(_decimal(data.get("paymentSummary", {}).get("totalDueSeller", {}).get("value", 0)))
                        if _decimal(data.get("paymentSummary", {}).get("totalDueSeller", {}).get("value", 0)) > 0
                        else None
                    ),
                    sold_via_ad_campaign=bool(data.get("properties", {}).get("soldViaAdCampaign", False)),
                    # Day 31-B: AD_FEE 合计写入 Order
                    ad_fee_total=float(total_ad_fee) if total_ad_fee > 0 else None,
                    # Day 31.5-A: tracking_no 从 shipping_fulfillment 子资源采集
                    tracking_no=tracking_no,
                )
                sess.add(new_order)

            sess.flush()

            # ── 获取现有 OrderItem，构建 sku → id 映射 ───────────────
            existing_items = {
                oi.sku: oi
                for oi in sess.query(OrderItem)
                .filter(OrderItem.order_id == order_id)
                .all()
            }
            incoming_skus = {d["sku"] for d in li_data}

            # ── 删除不再存在的 OrderItem ────────────────────────────
            for sku, oi in existing_items.items():
                if sku not in incoming_skus:
                    sess.delete(oi)

            # ── upsert OrderItem（幂等：同 order_id + sku 用 update）───────
            for d in li_data:
                oi = existing_items.get(d["sku"])
                if oi:
                    oi.quantity = d["quantity"]
                    oi.unit_price = float(d["unit_price"])
                    oi.sale_amount = float(d["sale_amount"])
                else:
                    sess.add(OrderItem(
                        order_id=order_id,
                        sku=d["sku"],
                        quantity=d["quantity"],
                        unit_price=float(d["unit_price"]),
                        sale_amount=float(d["sale_amount"]),
                    ))

            # ── 写 Transaction ─────────────────────────────────────────
            # SALE：按 line_item 逐条写（每 SKU 一条，幂等）
            for d in li_data:
                self._write_sale_transaction(
                    sess,
                    order_id=order_id,
                    sku=d["sku"],
                    quantity=d["quantity"],
                    sale_amount=d["sale_amount"],
                    order_date=order_date,
                    currency="USD",
                    unit_cost=d["product_cost"],
                )

            # FEE / SHIPPING / AD_FEE / SALE_TAX：订单级，只写一次（不在循环内）
            if total_fee > 0:
                self._write_fee_transaction(
                    sess,
                    order_id=order_id,
                    fee_amount=total_fee,
                    order_date=order_date,
                    currency="USD",
                )
            if shipping_cost > 0:
                self._write_shipping_transaction(
                    sess,
                    order_id=order_id,
                    shipping_cost=shipping_cost,
                    order_date=order_date,
                    currency="USD",
                )
            if total_ad_fee > 0:
                self._write_ad_fee_transaction(
                    sess,
                    order_id=order_id,
                    ad_fee_amount=total_ad_fee,
                    order_date=order_date,
                    currency="USD",
                )
            if total_sale_tax > 0:
                self._write_sale_tax_transaction(
                    sess,
                    order_id=order_id,
                    sale_tax_amount=total_sale_tax,
                    order_date=order_date,
                    currency="USD",
                )

            sess.commit()

        # ── 判断返回值 ───────────────────────────────────────────────
        # 全 SKU 无成本 → 视为 unlinked 订单，跳过
        if unlinked_skus and len(unlinked_skus) == len(li_data):
            return (False, unlinked_skus[0])
        return (True, None)

    def _write_sale_transaction(
        self,
        sess,
        order_id: str,
        sku: str,
        quantity: int,
        sale_amount: Decimal,
        order_date: datetime | None,
        currency: str,
        unit_cost: Decimal | None = None,
    ):
        """写 SALE 流水（幂等：每 order_id + sku 只写一次）"""
        has = sess.query(Transaction).filter(
            Transaction.order_id == order_id,
            Transaction.sku == sku,
            Transaction.type == TransactionType.SALE,
        ).first()
        if has:
            return
        total_cost_val: float | None = None
        profit_val: float | None = None
        margin_val: float | None = None
        amount_jpy_val: float | None = None
        exchange_rate_val: float | None = None

        if order_date is not None:
            try:
                amount_jpy, rate_used, _actual = convert(
                    sess,
                    Decimal(str(sale_amount)),
                    currency,
                    "JPY",
                    order_date.date(),
                )
                amount_jpy_val = float(amount_jpy)
                exchange_rate_val = float(rate_used)
            except RateNotFoundError:
                pass

        if unit_cost is not None:
            total_cost_val = float(unit_cost * quantity)
        if amount_jpy_val is not None and total_cost_val is not None:
            profit_val = amount_jpy_val - total_cost_val
            if amount_jpy_val > 0:
                margin_val = profit_val / amount_jpy_val
        sess.add(Transaction(
            order_id=order_id,
            sku=sku,
            type=TransactionType.SALE,
            amount=float(sale_amount),
            currency=currency,
            amount_jpy=amount_jpy_val,
            exchange_rate=exchange_rate_val,
            date=order_date,
            unit_cost=float(unit_cost) if unit_cost is not None else None,
            total_cost=total_cost_val,
            profit=profit_val,
            margin=margin_val,
        ))

    def _write_fee_transaction(
        self,
        sess,
        order_id: str,
        fee_amount: Decimal,
        order_date: datetime | None,
        currency: str,
    ):
        """写 FEE 流水（订单级，每 order_id 只写一条，sku=NULL）"""
        has = sess.query(Transaction).filter(
            Transaction.order_id == order_id,
            Transaction.type == TransactionType.FEE,
        ).first()
        if has:
            return
        amount_jpy_val: float | None = None
        exchange_rate_val: float | None = None
        if order_date is not None:
            try:
                amount_jpy, rate_used, _actual = convert(
                    sess,
                    Decimal(str(-fee_amount)),
                    currency,
                    "JPY",
                    order_date.date(),
                )
                amount_jpy_val = float(amount_jpy)
                exchange_rate_val = float(rate_used)
            except RateNotFoundError:
                pass
        sess.add(Transaction(
            order_id=order_id,
            sku=None,  # 订单级费用，无 SKU
            type=TransactionType.FEE,
            amount=float(-fee_amount),
            currency=currency,
            amount_jpy=amount_jpy_val,
            exchange_rate=exchange_rate_val,
            date=order_date,
        ))

    def _write_shipping_transaction(
        self,
        sess,
        order_id: str,
        shipping_cost: Decimal,
        order_date: datetime | None,
        currency: str,
    ):
        """写 SHIPPING 流水（订单级，每 order_id 只写一条，sku=NULL）"""
        has = sess.query(Transaction).filter(
            Transaction.order_id == order_id,
            Transaction.type == TransactionType.SHIPPING,
        ).first()
        if has:
            return
        amount_jpy_val: float | None = None
        exchange_rate_val: float | None = None
        if order_date is not None:
            try:
                amount_jpy, rate_used, _actual = convert(
                    sess,
                    Decimal(str(shipping_cost)),
                    currency,
                    "JPY",
                    order_date.date(),
                )
                amount_jpy_val = float(amount_jpy)
                exchange_rate_val = float(rate_used)
            except RateNotFoundError:
                pass
        sess.add(Transaction(
            order_id=order_id,
            sku=None,  # 订单级运费，无 SKU
            type=TransactionType.SHIPPING,
            amount=float(shipping_cost),
            currency=currency,
            amount_jpy=amount_jpy_val,
            exchange_rate=exchange_rate_val,
            date=order_date,
        ))

    def _write_ad_fee_transaction(
        self,
        sess,
        order_id: str,
        ad_fee_amount: Decimal,
        order_date: datetime | None,
        currency: str,
    ):
        """写 AD_FEE 流水（订单级，每 order_id 只写一条，sku=NULL，符号负数）"""
        has = sess.query(Transaction).filter(
            Transaction.order_id == order_id,
            Transaction.type == TransactionType.AD_FEE,
        ).first()
        if has:
            return
        amount_jpy_val: float | None = None
        exchange_rate_val: float | None = None
        if order_date is not None:
            try:
                amount_jpy, rate_used, _actual = convert(
                    sess,
                    Decimal(str(-ad_fee_amount)),
                    currency,
                    "JPY",
                    order_date.date(),
                )
                amount_jpy_val = float(amount_jpy)
                exchange_rate_val = float(rate_used)
            except RateNotFoundError:
                pass
        sess.add(Transaction(
            order_id=order_id,
            sku=None,  # 订单级广告费，无 SKU
            type=TransactionType.AD_FEE,
            amount=float(-ad_fee_amount),
            currency=currency,
            amount_jpy=amount_jpy_val,
            exchange_rate=exchange_rate_val,
            date=order_date,
        ))

    def _write_sale_tax_transaction(
        self,
        sess,
        order_id: str,
        sale_tax_amount: Decimal,
        order_date: datetime | None,
        currency: str,
    ):
        """写 SALE_TAX 流水（订单级，每 order_id 只写一条，sku=NULL，符号正数）"""
        has = sess.query(Transaction).filter(
            Transaction.order_id == order_id,
            Transaction.type == TransactionType.SALE_TAX,
        ).first()
        if has:
            return
        amount_jpy_val: float | None = None
        exchange_rate_val: float | None = None
        if order_date is not None:
            try:
                amount_jpy, rate_used, _actual = convert(
                    sess,
                    Decimal(str(sale_tax_amount)),
                    currency,
                    "JPY",
                    order_date.date(),
                )
                amount_jpy_val = float(amount_jpy)
                exchange_rate_val = float(rate_used)
            except RateNotFoundError:
                pass
        sess.add(Transaction(
            order_id=order_id,
            sku=None,  # 订单级销售税，无 SKU
            type=TransactionType.SALE_TAX,
            amount=float(sale_tax_amount),
            currency=currency,
            amount_jpy=amount_jpy_val,
            exchange_rate=exchange_rate_val,
            date=order_date,
        ))

    # ── Tracking 号采集 ──────────────────────────────────────────────

    def _fetch_tracking_no(self, order_id: str) -> str | None:
        """
        从 eBay shipping_fulfillment 子资源拉取 tracking 号。

        cpass 场景下返回的是 SpeedPAK 内部 ID(27-28 字符大写字母+数字)。
        若订单还未发货 / API 返回空 / 调用失败,均返回 None,不抛异常。
        """
        try:
            resp = self._client.get(
                f"/sell/fulfillment/v1/order/{order_id}/shipping_fulfillment"
            )
        except Exception as e:
            log.info("[tracking] {} shipping_fulfillment 调用失败: {}", order_id, e)
            return None

        fulfillments = resp.get("fulfillments", []) if resp else []
        if not fulfillments:
            return None

        # 取第一个 shipment 的 tracking(业务上一单一包,实际不会有多 shipment)
        first = fulfillments[0]
        tracking = first.get("shipmentTrackingNumber")
        return tracking if tracking else None

    # ── Finances API 缓存 ──────────────────────────────────────────

    def _fetch_finances_transactions(self, order_id: str) -> list[dict]:
        """
        一次 Finances API 调用，缓存结果供 FEE/AD_FEE/SALE_TAX 三次提取共用。

        Day 31-B 优化：将 3 次独立 API 调用合并为 1 次，避免重复请求。
        """
        try:
            resp = self._client.get(
                "/sell/finances/v1/transaction",
                params={"orderId": order_id},
            )
            return resp.get("transactions", [])
        except Exception as exc:
            log.debug("Finances API /transaction 查询失败 [{}]: {}", order_id, exc)
            return []

    # ── 费用提取（Day 28.5 修正 + Day 31-B 扩展）──────────────────────

    def _extract_fee_from_transactions(
        self, data: dict, order_id: str, transactions: list[dict]
    ) -> Decimal:
        """
        从 Finances API transactions 提取平台费（FEE）。

        遍历 transactionType=SALE 的 orderLineItems[].marketplaceFees[]，
        累加所有 feeType 的 amount。
        不取 NON_SALE_CHARGE（广告费，AD_FEE 单独采集）。

        备用：transactions 为空时用 Fulfillment API 的 totalMarketplaceFee.value。
        """
        total_fee = Decimal("0")
        for txn in transactions:
            if txn.get("transactionType") != "SALE":
                continue
            for li in txn.get("orderLineItems", []):
                for fee in li.get("marketplaceFees", []):
                    total_fee += _decimal(fee.get("amount", {}).get("value", 0))

        if total_fee > 0:
            return total_fee

        # 备用：Fulfillment API 的聚合值
        fallback = _decimal(
            data.get("totalMarketplaceFee", {}).get("value", 0)
        )
        if fallback > 0:
            log.info("[{}] Finances API 未返回 FEE，用 totalMarketplaceFee 兜底: {}", order_id, fallback)
            return fallback

        return total_fee

    def _extract_ad_fee_from_transactions(
        self, order_id: str, transactions: list[dict]
    ) -> Decimal:
        """
        从 Finances API transactions 提取 AD_FEE（广告费）。

        遍历 transactionType=NON_SALE_CHARGE 且 feeType=AD_FEE 的 transaction。
        符号为负数（写入 Transaction 时取负）。
        """
        for txn in transactions:
            if (
                txn.get("transactionType") == "NON_SALE_CHARGE"
                and txn.get("feeType") == "AD_FEE"
            ):
                return _decimal(txn.get("amount", {}).get("value", 0))
        return Decimal("0")

    def _extract_sale_tax_from_transactions(
        self, order_id: str, transactions: list[dict]
    ) -> Decimal:
        """
        从 Finances API transactions 提取 SALE_TAX（销售税）。

        遍历 transactionType=SALE 的 transaction，取 ebayCollectedTaxAmount。
        可能有多个 SALE transaction（多 SKU），累加所有。
        """
        total_tax = Decimal("0")
        for txn in transactions:
            if txn.get("transactionType") != "SALE":
                continue
            tax = _decimal(txn.get("ebayCollectedTaxAmount", {}).get("value", 0))
            total_tax += tax
        return total_tax

    def _extract_buyer_paid_total(self, data: dict) -> Decimal | None:
        """
        买家实际付款总额 = pricingSummary.total + Σ ebayCollectAndRemitTaxes[].amount

        不含税的 total 在 pricingSummary.total，含税部分在 ebayCollectAndRemitTaxes，
        两者相加才是买家银行卡真实扣款金额。

        如果 pricingSummary 缺失，返回 None（Order.buyer_paid_total 保持 null）。
        """
        price_total_val = data.get("pricingSummary", {}).get("total", {}).get("value")
        if price_total_val is None:
            return None
        total = _decimal(price_total_val)
        for tax_entry in data.get("ebayCollectAndRemitTaxes", []) or []:
            total += _decimal(tax_entry.get("amount", {}).get("value", 0))
        return total
