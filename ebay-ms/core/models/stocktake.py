"""
core/models/stocktake.py

库存盘点模型
"""

import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class StocktakeStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class Stocktake(Base, TimestampMixin):
    """
    库存盘点主表

    记录一次盘点的元信息：状态、操作人、开始/结束时间。
    """
    __tablename__ = "stocktakes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[StocktakeStatus] = mapped_column(
        Enum(StocktakeStatus),
        default=StocktakeStatus.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class StocktakeItem(Base):
    """
    盘点明细

    每行记录一个 SKU 的系统数量和实际清点数。
    """
    __tablename__ = "stocktake_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stocktake_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocktakes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.sku"), nullable=False, index=True
    )
    system_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="盘点开始时的系统可用库存"
    )
    actual_quantity: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="实际清点数量（None = 尚未清点）"
    )
    difference: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="差异 = actual - system（正数多，负数少）"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
