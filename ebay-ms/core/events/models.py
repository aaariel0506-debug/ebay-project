"""EventLog ORM model — 事件持久化"""
import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class EventStatus(enum.StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class EventLog(Base, TimestampMixin):
    """事件日志 — 持久化所有事件，支持重试和死信"""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus), nullable=False, default=EventStatus.PENDING, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handler_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
