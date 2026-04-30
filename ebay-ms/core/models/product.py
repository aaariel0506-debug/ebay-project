"""
core/models/product.py
Product 模型 — 商品主数据
SKU 是商品唯一标识
"""
import enum
from decimal import Decimal
from typing import Optional

from core.models.base import Base, TimestampMixin
from sqlalchemy import Enum, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ProductStatus(enum.StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    OUT_OF_STOCK = "out_of_stock"


class Product(Base, TimestampMixin):
    """
    商品主数据表。

    sku: 商品唯一标识（如 02-2603-0001）
    title: 商品名称（nullable，等待 D13 eBay 同步回填）
    asin: Amazon ASIN（B0XXXXXXXX）
    source_url: 采购链接
    variant_note: 自由文本变体说明（200m/赤/M号等）
    cost_price: 进货价（nullable，等待 Amazon CSV 注入）
    cost_currency: 进货货币，默认 JPY
    supplier: 供应商名称
    status: 商品状态（active/discontinued/out_of_stock）
    """
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    asin: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    variant_note: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    cost_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    cost_currency: Mapped[str] = mapped_column(String(3), default="JPY", nullable=False)
    supplier: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus),
        default=ProductStatus.ACTIVE,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_products_status", "status"),
        Index("ix_products_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<Product(sku={self.sku!r}, asin={self.asin!r}, status={self.status.value})>"
