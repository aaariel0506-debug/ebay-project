"""
matcher/order_shipment.py — 订单与快递匹配引擎

匹配策略（优先级从高到低）：
1. 已有 ebay_order_id 的 shipment → 直接确认（无需处理）
2. 精确单号匹配：shipment.cpass_transaction_id = ebay_order.tracking_number
   （CPass Order No. 就是 eBay 上显示的 Tracking Number，46/59 条可匹配）
3. 日期兜底：发货日期在 eBay 成交日 ±3 天内（适用于 Japan Post 等无法精确匹配的快递）

返回：
    {"matched": int, "unmatched": int, "confirmed": int}
"""
from datetime import datetime
from db.db import fetch_all, execute


def match_order_shipment() -> dict:
    """
    将 shipments 表与 ebay_orders 表进行匹配，更新 shipments.ebay_order_id

    Returns:
        {"matched": int, "unmatched": int, "confirmed": int}
    """
    matched_count = 0
    unmatched_count = 0

    # 获取所有 ebay_order_id 为空的 shipment
    unmatched_shipments = fetch_all("""
        SELECT * FROM shipments
        WHERE ebay_order_id IS NULL
        ORDER BY ship_date
    """)

    if not unmatched_shipments:
        confirmed = fetch_all("SELECT COUNT(*) as cnt FROM shipments WHERE ebay_order_id IS NOT NULL")[0]['cnt']
        return {"matched": 0, "unmatched": 0, "confirmed": confirmed}

    # 构建 eBay 订单索引：tracking_number → order（用于精确匹配）
    ebay_orders = fetch_all("SELECT * FROM ebay_orders ORDER BY sale_date")
    tracking_index: dict[str, dict] = {}
    for order in ebay_orders:
        tn = order.get('tracking_number')
        if tn:
            tracking_index[tn.strip()] = order

    for shipment in unmatched_shipments:
        matched_order = None

        # ── 策略 1：精确单号匹配 ──────────────────────────────────────────
        # CPass Order No. (cpass_transaction_id) 即 eBay Tracking Number
        cpass_id = shipment.get('cpass_transaction_id')
        if cpass_id:
            matched_order = tracking_index.get(cpass_id.strip())

        # ── 策略 2：日期兜底（±3 天，适用于 Japan Post 等）─────────────────
        if not matched_order:
            shipment_date = shipment.get('ship_date')
            if shipment_date:
                try:
                    s_date = datetime.strptime(shipment_date, '%Y-%m-%d')
                    for order in ebay_orders:
                        order_date = order.get('sale_date')
                        if not order_date:
                            continue
                        try:
                            o_date = datetime.strptime(order_date, '%Y-%m-%d')
                            date_diff = abs((s_date - o_date).days)
                            if date_diff <= 3:
                                matched_order = order
                                break
                        except (ValueError, TypeError):
                            continue
                except (ValueError, TypeError):
                    pass

        # ── 执行更新 ────────────────────────────────────────────────────
        if matched_order:
            rows_affected = execute(
                "UPDATE shipments SET ebay_order_id = ? WHERE id = ?",
                (matched_order['order_id'], shipment['id'])
            )
            if rows_affected > 0:
                matched_count += 1
            else:
                unmatched_count += 1
        else:
            unmatched_count += 1

    # 统计已有 ebay_order_id 的记录（已确认的）
    confirmed = fetch_all("SELECT COUNT(*) as cnt FROM shipments WHERE ebay_order_id IS NOT NULL")[0]['cnt']

    return {
        "matched": matched_count,
        "unmatched": unmatched_count,
        "confirmed": confirmed
    }
