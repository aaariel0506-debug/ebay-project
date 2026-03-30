"""
ingest/ebay_api.py — 通过 eBay REST API 拉取订单数据

使用的 API：
- Fulfillment API  GET /sell/fulfillment/v1/order
  → 获取订单列表（含 tracking number、shipping info 等）
- Finances API     GET /sell/finances/v1/transaction
  → 获取财务记录（含 eBay 平台费、广告费、实际收款额等）

两组数据以 order_id（legacyOrderId）为键做内存 join，写入 ebay_orders 表。
"""
import re
from datetime import datetime, timezone
from typing import Generator

import requests

from db.models import EbayOrder
from db.db import insert_many, fetch_all


FULFILLMENT_BASE = "https://api.ebay.com/sell/fulfillment/v1"
FINANCES_BASE = "https://api.ebay.com/sell/finances/v1"
PAGE_LIMIT = 200  # 每次 API 请求最多返回条数


# ──────────────────────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────────────────────

def _auth_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _parse_amount(amount_obj: dict | None) -> float | None:
    """解析 eBay API 返回的金额对象 {"value": "26.80", "currency": "USD"} → float"""
    if not amount_obj:
        return None
    try:
        return float(amount_obj.get("value", 0))
    except (ValueError, TypeError):
        return None


def _iso_to_date(iso: str | None) -> str | None:
    """ISO 8601 时间戳 → 'YYYY-MM-DD' 字符串"""
    if not iso:
        return None
    try:
        # 处理带时区的 ISO 字符串，如 "2026-02-01T10:22:33.000Z"
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _date_to_iso(date_str: str) -> str:
    """'YYYY-MM-DD' → ISO 8601 UTC 开始时间 'YYYY-MM-DDT00:00:00.000Z'"""
    return f"{date_str}T00:00:00.000Z"


# ──────────────────────────────────────────────────────────────
# Fulfillment API — 获取订单
# ──────────────────────────────────────────────────────────────

def _fetch_orders_page(access_token: str, params: dict) -> tuple[list[dict], str | None]:
    """
    拉取一页订单数据

    Returns:
        (orders_list, next_cursor)
    """
    url = f"{FULFILLMENT_BASE}/order"
    resp = requests.get(url, headers=_auth_headers(access_token), params=params, timeout=30)

    if resp.status_code == 401:
        raise PermissionError("eBay API 认证失败（401）—— 请重新运行 `python main.py auth`")
    if resp.status_code != 200:
        raise RuntimeError(f"Fulfillment API 错误: {resp.status_code} {resp.text[:300]}")

    data = resp.json()
    orders = data.get("orders", [])
    next_cursor = data.get("next")  # 翻页游标
    return orders, next_cursor


def fetch_all_orders(
    access_token: str,
    date_from: str,          # 'YYYY-MM-DD'
    date_to: str | None = None,  # 'YYYY-MM-DD'，默认今天
) -> Generator[dict, None, None]:
    """
    分页拉取所有订单，yield 每条原始订单 dict

    eBay Fulfillment API filter 语法：
        filter=lastmodifieddate:[2026-02-01T00:00:00.000Z..2026-02-28T23:59:59.000Z]
    """
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    date_filter = (
        f"lastmodifieddate:[{_date_to_iso(date_from)}..{date_to}T23:59:59.999Z]"
    )

    params = {
        "filter": date_filter,
        "limit": PAGE_LIMIT,
    }

    while True:
        orders, next_cursor = _fetch_orders_page(access_token, params)
        yield from orders
        if not next_cursor:
            break
        params["offset"] = next_cursor  # eBay 用 cursor 字符串作为 offset


# ──────────────────────────────────────────────────────────────
# Finances API — 获取费用
# ──────────────────────────────────────────────────────────────

def _fetch_transactions_page(access_token: str, params: dict) -> tuple[list[dict], str | None]:
    """拉取一页财务交易记录"""
    url = f"{FINANCES_BASE}/transaction"
    resp = requests.get(url, headers=_auth_headers(access_token), params=params, timeout=30)

    if resp.status_code == 401:
        raise PermissionError("eBay Finances API 认证失败（401）—— 请重新运行 `python main.py auth`")
    if resp.status_code != 200:
        # Finances API 可能未开通，非致命错误
        return [], None

    data = resp.json()
    transactions = data.get("transactions", [])
    next_cursor = data.get("next")
    return transactions, next_cursor


def fetch_order_fees(
    access_token: str,
    date_from: str,
    date_to: str | None = None,
) -> dict[str, dict]:
    """
    拉取所有财务交易记录，汇总为 {order_id: {"ebay_fee": ..., "ad_fee": ..., "net": ...}}

    交易类型：
    - SALE      → 销售收入
    - FEE       → eBay 平台费（含 Final Value Fee）
    - AD_FEE    → 广告费
    """
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    date_filter = (
        f"transactionDate:[{_date_to_iso(date_from)}..{date_to}T23:59:59.999Z]"
    )

    params = {
        "filter": date_filter,
        "limit": PAGE_LIMIT,
    }

    fee_map: dict[str, dict] = {}   # order_id → {"ebay_fee", "ad_fee", "net"}

    while True:
        transactions, next_cursor = _fetch_transactions_page(access_token, params)
        for tx in transactions:
            order_id = tx.get("orderId") or ""
            if not order_id:
                continue
            tx_type = tx.get("transactionType", "")
            amount = _parse_amount(tx.get("amount")) or 0.0

            entry = fee_map.setdefault(order_id, {"ebay_fee": 0.0, "ad_fee": 0.0, "net": 0.0})

            if tx_type == "SALE":
                entry["net"] += amount
            elif tx_type == "FEE":
                entry["ebay_fee"] += abs(amount)   # 费用为负值，取绝对值
            elif tx_type in ("AD_FEE", "ADS_FEE"):
                entry["ad_fee"] += abs(amount)

        if not next_cursor:
            break
        params["offset"] = next_cursor

    return fee_map


# ──────────────────────────────────────────────────────────────
# 主入口 — 解析订单并写入数据库
# ──────────────────────────────────────────────────────────────

def _parse_order(raw: dict, fees: dict[str, dict]) -> EbayOrder | None:
    """将 Fulfillment API 单条订单 dict 转换为 EbayOrder dataclass"""
    # legacyOrderId 是 eBay 销售报告里的 "Order Number"（如 03-14197-21396）
    order_id = raw.get("legacyOrderId") or raw.get("orderId")
    if not order_id:
        return None

    # 买家信息
    buyer = raw.get("buyer", {})
    buyer_username = buyer.get("username")

    # 订单行（通常每个订单一行，捆绑订单可能多行）
    line_items = raw.get("lineItems", [])
    item_title = None
    item_id = None
    quantity = 0
    if line_items:
        first = line_items[0]
        item_title = first.get("title")
        item_id = str(first.get("legacyItemId", "")) or None
        quantity = sum(li.get("quantity", 1) for li in line_items)

    # 价格明细
    pricing = raw.get("pricingSummary", {})
    sale_price = _parse_amount(pricing.get("priceSubtotal"))
    shipping_charged = _parse_amount(pricing.get("deliveryCost"))
    total_amount = _parse_amount(pricing.get("total"))

    # 快递追踪号（取第一个 fulfillment 的第一个 trackingNumber）
    tracking_number = None
    fulfillments = raw.get("fulfillmentHrefs", [])  # 有时是简单列表
    order_fulfillments = raw.get("fulfillmentStartInstructions", [])
    # 更可靠的路径：getOrder 详情里的 fulfillmentStartInstructions → finalDestinationAddress
    # 但批量 getOrders 里有 shippingFulfillments
    shipping_fulfillments = raw.get("shippingFulfillments", [])
    for sf in shipping_fulfillments:
        tns = sf.get("trackingNumber")
        if tns:
            tracking_number = tns
            break

    # 发货地国家
    ship_to = raw.get("fulfillmentStartInstructions", [{}])[0] if raw.get("fulfillmentStartInstructions") else {}
    ship_to_address = ship_to.get("finalDestinationAddress", {}) if isinstance(ship_to, dict) else {}
    country = ship_to_address.get("countryCode")

    # 订单状态
    order_status = raw.get("orderFulfillmentStatus") or raw.get("orderPaymentStatus")

    # 成交日期
    sale_date = _iso_to_date(raw.get("creationDate"))

    # 费用数据（来自 Finances API）
    fee_data = fees.get(order_id) or fees.get(raw.get("orderId", "")) or {}
    ebay_fee = fee_data.get("ebay_fee")
    ad_fee = fee_data.get("ad_fee")
    net = fee_data.get("net") or total_amount  # 如果 Finances API 没数据，用总价代替

    return EbayOrder(
        order_id=order_id,
        sale_date=sale_date,
        buyer_username=buyer_username,
        item_title=item_title,
        item_id=item_id,
        quantity=quantity or 1,
        sale_price_usd=sale_price,
        shipping_charged_usd=shipping_charged,
        ebay_fee_usd=ebay_fee,
        ebay_ad_fee_usd=ad_fee,
        payment_net_usd=net,
        order_status=order_status,
        shipping_address_country=country,
        tracking_number=tracking_number,
    )


def ingest_ebay_api(
    access_token: str,
    date_from: str,
    date_to: str | None = None,
    fetch_fees: bool = True,
) -> int:
    """
    通过 eBay API 拉取订单并写入数据库

    Args:
        access_token: eBay OAuth 2.0 access token
        date_from:    开始日期 'YYYY-MM-DD'
        date_to:      结束日期 'YYYY-MM-DD'（默认今天）
        fetch_fees:   是否拉取 Finances API 费用数据

    Returns:
        实际插入的记录数
    """
    print(f"[api] 正在拉取 eBay 订单（{date_from} ~ {date_to or '今天'}）...")

    # 先拉取费用数据（可选）
    fees: dict[str, dict] = {}
    if fetch_fees:
        print("[api] 正在拉取财务数据（Finances API）...")
        try:
            fees = fetch_order_fees(access_token, date_from, date_to)
            print(f"[api] 获取到 {len(fees)} 条财务记录")
        except Exception as e:
            print(f"[api] 财务数据拉取失败（非致命）: {e}")

    # 拉取订单
    orders = []
    order_count = 0
    for raw in fetch_all_orders(access_token, date_from, date_to):
        order_count += 1
        ebay_order = _parse_order(raw, fees)
        if ebay_order:
            orders.append(ebay_order.to_dict())

    print(f"[api] 获取到 {order_count} 条原始订单，解析有效 {len(orders)} 条")

    if orders:
        inserted = insert_many("ebay_orders", orders)
        return inserted
    return 0
