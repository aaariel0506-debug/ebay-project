"""Inventory ORM — 库存变动流水模型"""
import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class InventoryType(enum.StrEnum):
    IN = "in"            # 入库
    OUT = "out"          # 出库
    ADJUST = "adjust"    # 调整
    RETURN = "return"    # 退回


class Inventory(Base, TimestampMixin):
    """
    库存变动流水

    关联：sku -> Product.sku（外键）
    """
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.sku"), nullable=False, index=True
    )
    type: Mapped[InventoryType] = mapped_column(
        Enum(InventoryType), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, doc="变动数量（正数）")
    related_order: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, doc="关联 eBay Order ID"
    )
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, doc="实际发生时间")
