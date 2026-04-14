"""
core/models/product.py
Product 模型 — 商品主数据
SKU 是商品唯一标识
"""
import enum
from decimal import Decimal

from core.models.base import Base, TimestampMixin
from sqlalchemy import Enum, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    OUT_OF_STOCK = "out_of_stock"


class Product(Base, TimestampMixin):
    """
    商品主数据表。

    sku: 商品唯一标识（如 02-2603-0001）
    title: 商品名称
    category: 商品类别
    source_url: 采购链接
    cost_price: 进货价
    cost_currency: 进货货币，默认 JPY
    supplier: 供应商名称
    status: 商品状态（active/discontinued/out_of_stock）
    """
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_currency: Mapped[str] = mapped_column(String(3), default="JPY", nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
        return f"<Product(sku={self.sku!r}, title={self.title!r}, status={self.status.value})>"
