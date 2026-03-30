"""
ingest/ebay_orders.py — 导入 eBay Seller Hub 导出的 CSV 订单数据

真实 CSV 格式说明：
- 第 0 行为空白/元数据行，第 1 行为真正的表头 → pandas header=1
- 金额字段含货币前缀，如 "AU $376.51"、"$26.80"，需剥离
- item_id (Item Number) 可能被 pandas 解析为浮点数，需转字符串
- 含 "Tracking Number" 列，用于和 CPass Order No. 匹配
"""
import re
import pandas as pd
from datetime import datetime
from db.models import EbayOrder
from db.db import insert_many


def parse_currency(value) -> float | None:
    """
    解析金额字段：去掉货币符号、前缀（如 "AU $376.51" → 376.51）
    支持：$N, AU $N, USD $N, NaN, None, ''
    """
    if value is None or value == '':
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return float(value)
    # 去掉所有非数字字符，保留负号、小数点
    cleaned = re.sub(r'[^\d.\-]', '', str(value)).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(value) -> str | None:
    """解析日期字段，统一转 YYYY-MM-DD 格式"""
    if value is None or value == '':
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        if isinstance(value, (datetime, pd.Timestamp)):
            return pd.Timestamp(value).strftime('%Y-%m-%d')
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d', '%b %d, %Y']:
            try:
                return datetime.strptime(str(value).strip(), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return pd.to_datetime(value).strftime('%Y-%m-%d')
    except Exception:
        return None


def ingest_ebay_orders(file_path: str) -> int:
    """
    读取 eBay Seller Hub 导出的 CSV，写入 ebay_orders 表

    Args:
        file_path: CSV 文件路径

    Returns:
        实际插入的记录数
    """
    # 真实 eBay 销售报告：第 0 行是空白/标题行，第 1 行是列头
    try:
        df = pd.read_csv(file_path, header=1, dtype=str)
    except Exception:
        # 回退：尝试标准 header=0
        df = pd.read_csv(file_path, dtype=str)

    # 标准化列名（去掉前后空格）
    df.columns = df.columns.str.strip()

    # 如果 header=1 解析后第一列名为空或含"Order"字样，说明正确
    # 否则第一行可能就是数据行，回退到 header=0
    if df.empty:
        return 0

    orders = []
    for _, row in df.iterrows():
        def get_str(col: str) -> str | None:
            val = row.get(col)
            if val is None:
                return None
            s = str(val).strip()
            if s.lower() in ('nan', 'none', ''):
                return None
            return s

        # 订单号（必须字段）
        order_id = get_str('Order Number') or get_str('Order Id') or get_str('order_id')
        if not order_id:
            continue

        # item_id：eBay Item Number 可能是浮点数字符串 "3.97e+11"，转为整数字符串
        raw_item_id = get_str('Item Number') or get_str('Item Id') or get_str('item_id')
        if raw_item_id:
            try:
                item_id = str(int(float(raw_item_id)))
            except (ValueError, OverflowError):
                item_id = raw_item_id
        else:
            item_id = None

        # 数量
        qty_raw = get_str('Quantity') or get_str('quantity')
        try:
            quantity = int(float(qty_raw)) if qty_raw else 1
        except (ValueError, TypeError):
            quantity = 1

        order = EbayOrder(
            order_id=order_id,
            sale_date=parse_date(row.get('Sale Date', row.get('sale_date'))),
            buyer_username=get_str('Buyer Username') or get_str('buyer_username'),
            item_title=get_str('Item Title') or get_str('item_title'),
            item_id=item_id,
            quantity=quantity,
            sale_price_usd=parse_currency(row.get('Sold For', row.get('Total Sale Price', row.get('sale_price_usd')))),
            shipping_charged_usd=parse_currency(row.get('Shipping And Handling', row.get('Shipping Price', row.get('shipping_charged_usd')))),
            ebay_fee_usd=parse_currency(row.get('Final Value Fee', row.get('ebay_fee_usd'))),
            ebay_ad_fee_usd=parse_currency(row.get('Promoted Listing Fee', row.get('ebay_ad_fee_usd'))),
            payment_net_usd=parse_currency(row.get('Net Amount', row.get('payment_net_usd'))),
            order_status=get_str('Order Status') or get_str('order_status'),
            shipping_address_country=get_str('Ship To Country') or get_str('shipping_address_country'),
            tracking_number=get_str('Tracking Number') or get_str('tracking_number'),
        )
        orders.append(order.to_dict())

    if orders:
        return insert_many('ebay_orders', orders)
    return 0
