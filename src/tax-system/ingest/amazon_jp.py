"""
ingest/amazon_jp.py — 导入日本亚马逊 CSV 订单数据
"""
import pandas as pd
from datetime import datetime
from db.models import Purchase
from db.db import insert_many


def parse_value(value):
    """
    解析 CSV 字段值，处理各种特殊格式：
    - 「該当無し」→ None
    - Excel 公式格式 ="6321" → 6321
    - 带引号的值 "123" → 123
    - 空字符串 → None
    """
    if pd.isna(value) or value is None:
        return None

    str_val = str(value).strip()

    # 空字符串或「該当無し」表示空值
    if not str_val or str_val == '該当無し':
        return None

    # Excel 公式格式：="6321"
    if str_val.startswith('="') and str_val.endswith('"'):
        str_val = str_val[2:-1]  # 去掉 =" 和 "

    # 去掉普通的引号
    str_val = str_val.strip('"').strip("'")

    # 再次检查是否为空或該当無し
    if not str_val or str_val == '該当無し':
        return None

    return str_val


def parse_date(value) -> str | None:
    """
    解析日期字段，YYYY/MM/DD → YYYY-MM-DD
    """
    parsed = parse_value(value)
    if not parsed:
        return None

    try:
        # 尝试 YYYY/MM/DD 格式
        for fmt in ['%Y/%m/%d', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S']:
            try:
                return datetime.strptime(parsed, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        # 最后尝试 pandas 解析
        return pd.to_datetime(parsed).strftime('%Y-%m-%d')
    except Exception:
        return None


def parse_number(value) -> float | None:
    """
    解析数字字段，去掉引号和逗号后转 float
    """
    parsed = parse_value(value)
    if not parsed:
        return None

    try:
        # 去掉逗号
        cleaned = parsed.replace(',', '')
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value) -> int | None:
    """
    解析整数字段
    """
    parsed = parse_value(value)
    if not parsed:
        return None

    try:
        cleaned = parsed.replace(',', '')
        return int(float(cleaned))
    except ValueError:
        return None


def ingest_amazon_jp(file_path: str) -> int:
    """
    读取日本亚马逊 CSV，写入 purchases 表

    CSV 列名映射：
    - id: 自动生成 amazon_jp_{注文番号}_{ASIN}
    - platform: 固定 "amazon_jp"
    - purchase_date: 注文日
    - item_name: 商品名
    - item_sku: ASIN
    - quantity: 商品の数量
    - unit_price_jpy: 商品の価格（注文時の税抜金額）
    - total_price_jpy: 商品の小計（税込）
    - tax_jpy: 商品の小計（消費税）
    - shipping_fee_jpy: 商品の配送料および手数料（税込）
    - order_number: 注文番号

    Args:
        file_path: CSV 文件路径

    Returns:
        实际插入的记录数
    """
    # 用 pandas 读取 CSV，UTF-8 with BOM 编码
    df = pd.read_csv(file_path, encoding='utf-8-sig')

    # 标准化列名（去掉前后空格）
    df.columns = df.columns.str.strip()

    purchases = []
    for _, row in df.iterrows():
        # 获取关键字段
        order_number = parse_value(row.get('注文番号'))
        asin = parse_value(row.get('ASIN'))

        # 跳过无效行（缺少注文番号或 ASIN）
        if not order_number or not asin:
            continue

        # 生成唯一 ID：amazon_jp_{注文番号}_{ASIN}
        purchase_id = f"amazon_jp_{order_number}_{asin}"

        purchase = Purchase(
            id=purchase_id,
            platform='amazon_jp',
            purchase_date=parse_date(row.get('注文日')),
            item_name=parse_value(row.get('商品名')),
            item_name_en=None,  # 亚马逊 CSV 不含英文名
            item_sku=asin,
            quantity=parse_int(row.get('商品の数量')) or 1,
            unit_price_jpy=parse_number(row.get('商品の価格（注文時の税抜金額）')),
            total_price_jpy=parse_number(row.get('商品の小計（税込）')),
            tax_jpy=parse_number(row.get('商品の小計（消費税）')),
            shipping_fee_jpy=parse_number(row.get('商品の配送料および手数料（税込）')),
            order_number=order_number,
            receipt_image_path=None,
            needs_review=False,
            notes=None,
        )
        purchases.append(purchase.to_dict())

    # 调用 db.insert_many() 写入
    if purchases:
        return insert_many('purchases', purchases)
    return 0
