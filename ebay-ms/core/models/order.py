"""Order ORM — eBay 订单数据模型"""
import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Order(Base, TimestampMixin):
    """
    eBay 订单（订单级数据）

    Relationships:
        items -> OrderItem (1:N, cascade delete)
    """
    __tablename__ = "orders"

    ebay_order_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, doc="eBay Order ID（PK）"
    )
    # sale_price: 订单总额 = sum(OrderItem.sale_amount)，不再是单 SKU 字段
    sale_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    ebay_fee: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    buyer_country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING, index=True
    )
    order_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ship_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        doc="承运商 tracking 号(cpass 场景下为 SpeedPAK 内部 ID)",
    )
    buyer_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    shipping_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ad_fee_total: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        doc="订单级广告费合计(原币),Day 31-B 守恒不变式用",
    )
    buyer_paid_total: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        doc="买家实付总额(eBay pricingSummary.total,原币),Day 31-B 对账用",
    )
    total_due_seller_raw: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        doc="paymentSummary.totalDueSeller(原币)，卖家到手金额。Day 32+ 精确对账用。",
    )
    sold_via_ad_campaign: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True,
        doc="properties.soldViaAdCampaign，是否为广告订单。Day 31-B AD_FEE 采集 hint。",
    )

    # 子表
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OrderItem(Base, TimestampMixin):
    """
    订单明细（每张 order 的每个 SKU 一行）

    对应 eBay Fulfillment API 的 lineItems。
    一个 eBay 订单可以有多个 SKU，每个 SKU 对应一条 OrderItem。
    """
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("orders.ebay_order_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("products.sku"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    sale_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # relationship
    order: Mapped["Order"] = relationship("Order", back_populates="items")

    __table_args__ = (
        # 同一个 order 内 sku 不重复（幂等性约束）
        UniqueConstraint("order_id", "sku", name="uq_order_items_order_sku"),
    )
