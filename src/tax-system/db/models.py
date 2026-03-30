"""
db/models.py — 数据模型（Python dataclass，不依赖任何 ORM）
与 db/schema.sql 的表结构一一对应
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Purchase:
    """采购记录 — 对应 purchases 表"""
    id: str                             # 内部唯一ID（建议格式: {platform}_{order_number}）
    platform: str                       # amazon_jp / hobonichi / bandai / offline / other
    purchase_date: Optional[date] = None
    item_name: Optional[str] = None     # 商品名称（日文）
    item_name_en: Optional[str] = None  # 商品名称（英文，可选）
    item_sku: Optional[str] = None
    quantity: int = 1
    unit_price_jpy: Optional[float] = None
    total_price_jpy: Optional[float] = None
    tax_jpy: Optional[float] = None
    shipping_fee_jpy: Optional[float] = None
    order_number: Optional[str] = None  # 采购平台订单号
    receipt_image_path: Optional[str] = None  # 线下领收书照片路径
    needs_review: bool = False          # OCR低置信度，需人工复核
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "purchase_date": str(self.purchase_date) if self.purchase_date else None,
            "item_name": self.item_name,
            "item_name_en": self.item_name_en,
            "item_sku": self.item_sku,
            "quantity": self.quantity,
            "unit_price_jpy": self.unit_price_jpy,
            "total_price_jpy": self.total_price_jpy,
            "tax_jpy": self.tax_jpy,
            "shipping_fee_jpy": self.shipping_fee_jpy,
            "order_number": self.order_number,
            "receipt_image_path": self.receipt_image_path,
            "needs_review": int(self.needs_review),
            "notes": self.notes,
        }


@dataclass
class EbayOrder:
    """eBay 订单 — 对应 ebay_orders 表"""
    order_id: str                           # eBay 订单号（主键）
    sale_date: Optional[date] = None
    buyer_username: Optional[str] = None
    item_title: Optional[str] = None
    item_id: Optional[str] = None           # eBay Item ID
    quantity: int = 1
    sale_price_usd: Optional[float] = None
    shipping_charged_usd: Optional[float] = None  # 向买家收取的运费
    ebay_fee_usd: Optional[float] = None
    ebay_ad_fee_usd: Optional[float] = None
    payment_net_usd: Optional[float] = None       # 实际到账金额
    order_status: Optional[str] = None
    shipping_address_country: Optional[str] = None
    tracking_number: Optional[str] = None  # eBay 快递单号（用于匹配 CPass Order No.）

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "sale_date": str(self.sale_date) if self.sale_date else None,
            "buyer_username": self.buyer_username,
            "item_title": self.item_title,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "sale_price_usd": self.sale_price_usd,
            "shipping_charged_usd": self.shipping_charged_usd,
            "ebay_fee_usd": self.ebay_fee_usd,
            "ebay_ad_fee_usd": self.ebay_ad_fee_usd,
            "payment_net_usd": self.payment_net_usd,
            "order_status": self.order_status,
            "shipping_address_country": self.shipping_address_country,
            "tracking_number": self.tracking_number,
        }


@dataclass
class Shipment:
    """快递记录 — 对应 shipments 表"""
    id: str                                       # 内部唯一ID
    carrier: str                                  # cpass_speedpak / cpass_fedex / japanpost
    tracking_number: Optional[str] = None
    ebay_order_id: Optional[str] = None           # 关联eBay订单（可为空待匹配）
    ship_date: Optional[date] = None
    shipping_fee_usd: Optional[float] = None
    cpass_transaction_id: Optional[str] = None    # CPass适用
    jp_post_email_path: Optional[str] = None      # Japan Post邮件路径

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "carrier": self.carrier,
            "tracking_number": self.tracking_number,
            "ebay_order_id": self.ebay_order_id,
            "ship_date": str(self.ship_date) if self.ship_date else None,
            "shipping_fee_usd": self.shipping_fee_usd,
            "cpass_transaction_id": self.cpass_transaction_id,
            "jp_post_email_path": self.jp_post_email_path,
        }


@dataclass
class OrderBundle:
    """
    聚合视图 — 一个 eBay 订单及其关联的采购和快递信息
    由 matcher 引擎组装，供 generator 使用，不直接对应数据库表
    """
    ebay_order: EbayOrder
    purchases: list[Purchase] = field(default_factory=list)
    shipments: list[Shipment] = field(default_factory=list)
    match_method: Optional[str] = None   # sku / fuzzy / date_price / manual / unmatched
    confidence: Optional[float] = None   # 匹配置信度 0~1

    @property
    def is_fully_matched(self) -> bool:
        return bool(self.purchases) and bool(self.shipments)

    @property
    def total_purchase_cost_jpy(self) -> float:
        return sum(p.total_price_jpy or 0 for p in self.purchases)

    @property
    def total_shipping_fee_usd(self) -> float:
        return sum(s.shipping_fee_usd or 0 for s in self.shipments)
