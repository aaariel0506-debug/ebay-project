"""Exchange rate ORM model."""

from datetime import date as date_type
from decimal import Decimal

from core.models.base import Base, TimestampMixin
from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ExchangeRate(Base, TimestampMixin):
    """
    每日汇率。方向: from_currency -> to_currency。
    语义: 1 单位 from_currency = rate 单位 to_currency。
    例: 1 USD = 149.85 JPY。
    """

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint(
            "rate_date",
            "from_currency",
            "to_currency",
            name="uq_exchange_rates_date_pair",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rate_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="csv")
