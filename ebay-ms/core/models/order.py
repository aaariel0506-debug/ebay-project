"""Order ORM — eBay 订单数据模型"""
import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Order(Base, TimestampMixin):
    """
    eBay 订单

    关联：sku -> Product.sku（外键）
    """
    __tablename__ = "orders"

    ebay_order_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, doc="eBay Order ID（PK）"
    )
    sku: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.sku"), nullable=False, index=True
    )
    sale_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    ebay_fee: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    buyer_country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING, index=True
    )
    order_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ship_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    shipping_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
