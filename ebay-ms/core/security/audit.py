"""AuditLog — 敏感操作审计"""
from datetime import datetime, timezone

from core.models.base import Base, TimestampMixin
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class AuditLog(Base, TimestampMixin):
    """审计日志 — 记录所有敏感操作"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


def audit_log(action: str, operator: str, detail: dict | None = None, ip_address: str | None = None) -> AuditLog:
    """一行代码记录审计日志"""
    from core.database.connection import get_session

    record = AuditLog(
        action=action,
        operator=operator,
        detail=detail or {},
        ip_address=ip_address,
        timestamp=datetime.now(timezone.utc),
    )
    with get_session() as s:
        s.add(record)
        s.commit()
        s.refresh(record)
    return record
