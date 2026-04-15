"""
core/models/price_history.py

Day 16: 供应价格历史记录表

每次更新进货价时，旧价格存入此表。
用于追踪供应商价格变动、分析利润影响。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from core.models.base import Base, TimestampMixin
from sqlalchemy import Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from core.models.product import Product


class PriceChangeDirection(str):
    """价格变化方向枚举。"""
    UP = "up"
    DOWN = "down"
    UNCHANGED = "unchanged"


class SupplierPriceHistory(Base, TimestampMixin):
    """
    供应商价格历史记录表。

    每条记录 = 一次价格快照（不变也记录，用于追踪历史）。
    更新进货价时，旧价格自动写入此表。
    """
    __tablename__ = "supplier_price_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("products.sku", ondelete="CASCADE"),
        nullable=False,
    )
    supplier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="JPY", nullable=False)
    recorded_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # 关联 product（方便 join）
    product: Mapped["Product"] = relationship(  # type: ignore[valid-type]
        "Product",
        back_populates="_price_history",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_supplier_price_history_sku", "sku"),
        Index("ix_supplier_price_history_recorded_at", "recorded_at"),
        Index("ix_supplier_price_history_sku_recorded", "sku", "recorded_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SupplierPriceHistory(sku={self.sku!r}, price={self.price}, "
            f"currency={self.currency}, recorded_at={self.recorded_at})>"
        )

    @property
    def direction(self) -> str:
        """变化方向需要对比前一条记录，在 service 层判断。"""
        return "unknown"
