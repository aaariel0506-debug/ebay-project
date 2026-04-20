"""Transaction ORM — 财务流水模型"""
import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class TransactionType(enum.StrEnum):
    SALE = "sale"
    REFUND = "refund"
    FEE = "fee"
    SHIPPING = "shipping"
    ADJUSTMENT = "adjustment"


class Transaction(Base, TimestampMixin):
    """
    财务流水

    关联：order_id -> Order.ebay_order_id（外键）
         sku -> Product.sku（外键）
    """
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("orders.ebay_order_id"), nullable=True, index=True
    )
    sku: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("products.sku"), nullable=True, index=True
    )
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    amount_usd: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    exchange_rate: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Cost and profit (COGS)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    profit: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    margin: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
