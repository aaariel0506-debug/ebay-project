"""
ingest/cpass.py — 导入 CPass 快递数据（支持 XLSX 和 CSV）

真实 XLSX 格式说明（cpass1772897592924.xlsx）：
列名：Order No. | Carrier Name | Carrier Tracking No. | Destination |
      eBay Transaction ID | SKU Description | HSCODE

字段映射：
- id                 = cpass_{Order No.}
- cpass_transaction_id = Order No.          （Orange Connex 单号，= eBay Tracking Number）
- tracking_number    = Carrier Tracking No. （下游承运商单号，FedEx/SpeedPak 实际面单号）
- carrier            = 根据 Carrier Name 推断：NaN → cpass_speedpak, FedEx → cpass_fedex
- ebay_order_id      = eBay Transaction ID  （若 CSV 已填写）
- ship_date          = 无此列，留空
- shipping_fee_usd   = 无此列，留空
"""
import re
import pandas as pd
from datetime import datetime
from db.models import Shipment
from db.db import insert_many


def _is_empty(val) -> bool:
    """判断值是否为空/NaN"""
    if val is None:
        return True
    if isinstance(val, float):
        import math
        return math.isnan(val)
    s = str(val).strip()
    return s == '' or s.lower() in ('nan', 'none', 'n/a')


def get_str(val) -> str | None:
    """将 cell 值转为字符串，空/NaN 返回 None"""
    if _is_empty(val):
        return None
    s = str(val).strip()
    return s if s else None


def parse_date(value) -> str | None:
    """解析日期字段，统一转 YYYY-MM-DD 格式"""
    if _is_empty(value):
        return None
    try:
        if isinstance(value, (datetime, pd.Timestamp)):
            return pd.Timestamp(value).strftime('%Y-%m-%d')
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d']:
            try:
                return datetime.strptime(str(value).strip(), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return pd.to_datetime(value).strftime('%Y-%m-%d')
    except Exception:
        return None


def parse_currency(value) -> float | None:
    """解析金额字段（去掉 $ 和逗号），返回 float 或 None"""
    if _is_empty(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r'[^\d.\-]', '', str(value)).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _infer_carrier(carrier_name_raw: str | None) -> str:
    """
    根据 Carrier Name 推断 carrier 字段值

    规则：
    - NaN / 空 → 'cpass_speedpak'
    - 含 'fedex'（不区分大小写）→ 'cpass_fedex'
    - 其他 → 'cpass_' + 原始值（小写，空格替换为_）
    """
    if not carrier_name_raw:
        return 'cpass_speedpak'
    lower = carrier_name_raw.lower().strip()
    if not lower:
        return 'cpass_speedpak'
    if 'fedex' in lower:
        return 'cpass_fedex'
    if 'speedpak' in lower:
        return 'cpass_speedpak'
    # 保留原始值，加前缀
    normalized = lower.replace(' ', '_')
    return f'cpass_{normalized}'


def _read_file(file_path: str) -> pd.DataFrame:
    """根据扩展名读取 CSV 或 XLSX，返回 DataFrame"""
    lower = file_path.lower()
    if lower.endswith('.xlsx') or lower.endswith('.xls'):
        return pd.read_excel(file_path, dtype=str)
    else:
        return pd.read_csv(file_path, dtype=str)


def ingest_cpass(file_path: str) -> int:
    """
    解析 CPass 快递文件（XLSX 或 CSV），写入 shipments 表

    Args:
        file_path: XLSX 或 CSV 文件路径

    Returns:
        实际插入的记录数
    """
    df = _read_file(file_path)

    # 标准化列名（去掉前后空格）
    df.columns = df.columns.str.strip()

    shipments = []
    for _, row in df.iterrows():
        # 获取 Order No.（主键，必须字段）
        order_no = get_str(row.get('Order No.') or row.get('Order No'))
        if not order_no:
            continue

        # 生成内部 id
        shipment_id = f'cpass_{order_no}'

        # 承运商
        carrier_raw = get_str(row.get('Carrier Name'))
        carrier = _infer_carrier(carrier_raw)

        # 下游承运商追踪号（FedEx/SpeedPak 面单号）
        tracking_number = get_str(row.get('Carrier Tracking No.') or row.get('Carrier Tracking No'))

        # eBay 订单关联：CPass 的 eBay Transaction ID 格式与订单号不一致，
        # 留空 NULL，由 matcher 通过 tracking_number 匹配后填充
        ebay_order_id = None

        # 发货日期（此数据源无此列，留空）
        ship_date = parse_date(row.get('Ship Date') or row.get('ship_date'))

        # 运费（此数据源无此列，留空）
        shipping_fee_usd = parse_currency(row.get('Shipping Fee') or row.get('shipping_fee_usd'))

        shipment = Shipment(
            id=shipment_id,
            carrier=carrier,
            tracking_number=tracking_number,
            ebay_order_id=ebay_order_id,
            ship_date=ship_date,
            shipping_fee_usd=shipping_fee_usd,
            cpass_transaction_id=order_no,
            jp_post_email_path=None,
        )
        shipments.append(shipment.to_dict())

    if shipments:
        return insert_many('shipments', shipments)
    return 0
