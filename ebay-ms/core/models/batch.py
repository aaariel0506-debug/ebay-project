"""BatchProgress ORM — 批量导入中断续传进度记录。"""


from core.models.base import Base, TimestampMixin
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class BatchProgress(TimestampMixin, Base):
    """记录批量导入的进度，支持中断后从断点恢复。"""

    __tablename__ = "batch_progress"

    batch_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    last_row: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=-1,
        comment="最后处理的行号（0-indexed）",
    )
    total_rows: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="总行数",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="in_progress",
        comment="in_progress / completed / failed",
    )

    def __repr__(self) -> str:
        return f"<BatchProgress {self.batch_id} row={self.last_row}>"
