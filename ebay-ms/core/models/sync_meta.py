"""SyncMeta ORM — 记录各模块最后同步时间"""
from datetime import datetime

from core.models.base import Base
from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class SyncMeta(Base):
    """
    追踪各模块最后同步时间。

    用于增量同步：每次 sync 时更新 last_sync_at，下次 sync 从该时间开始。
    行级锁（module + operation 唯一）保证并发安全。
    """
    __tablename__ = "sync_meta"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_key: Mapped[str | None] = mapped_column(String(128), nullable=True, doc="上次同步的最后一条记录标识（如 orderId 等）")
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        UniqueConstraint("module", "operation", name="uq_sync_meta_module_operation"),
    )


def get_last_sync(session, module: str, operation: str) -> datetime | None:
    """查询某模块某操作的 last_sync_at。"""
    row = session.query(SyncMeta).filter(
        SyncMeta.module == module,
        SyncMeta.operation == operation,
    ).first()
    return row.last_sync_at if row else None


def set_last_sync(
    session,
    module: str,
    operation: str,
    sync_at: datetime,
    sync_key: str | None = None,
) -> None:
    """更新某模块某操作的 last_sync_at（upsert）。"""
    row = session.query(SyncMeta).filter(
        SyncMeta.module == module,
        SyncMeta.operation == operation,
    ).first()
    if row:
        row.last_sync_at = sync_at
        row.last_sync_key = sync_key
    else:
        session.add(SyncMeta(
            module=module,
            operation=operation,
            last_sync_at=sync_at,
            last_sync_key=sync_key,
        ))
