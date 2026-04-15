"""
core/models/inbound.py

入库单模型 — 记录供应商发货到仓库的收货流程
"""

import enum
from datetime import datetime
from decimal import Decimal

from core.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class InboundStatus(enum.StrEnum):
    PENDING = "pending"       # 待发货（供应商还未发）
    SHIPPED = "shipped"       # 已发货（在途）
    PARTIAL = "partial"       # 部分到货
    RECEIVED = "received"     # 全部到货
    CANCELLED = "cancelled"   # 取消


class InboundReceipt(Base, TimestampMixin):
    """
    入库单主表

    代表一次供应商发货事件。
    """
    __tablename__ = "inbound_receipts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    receipt_no: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True,
        doc="入库单号，如 IN-2026-04-16-001"
    )
    supplier: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[InboundStatus] = mapped_column(
        Enum(InboundStatus),
        default=InboundStatus.PENDING,
        nullable=False,
        index=True,
    )
    expected_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)


class InboundReceiptItem(Base):
    """
    入库单项

    一张入库单包含多个 SKU 行。
    """
    __tablename__ = "inbound_receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inbound_receipts.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.sku"), nullable=False, index=True
    )
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False, doc="预期数量")
    received_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, doc="实际收货数量")
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, doc="进货单价")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_inbound_items_receipt_sku", "receipt_id", "sku"),
    )
