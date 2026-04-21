"""create sync_meta table

Revision ID: fcfeddfffc4f
Revises: b8d46d8c3b34
Create Date: 2026-04-21 14:55:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "fcfeddfffc4f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b8d46d8c3b34"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sync_meta (
            id INTEGER NOT NULL,
            module VARCHAR(32) NOT NULL,
            operation VARCHAR(32) NOT NULL,
            last_sync_at DATETIME,
            last_sync_key VARCHAR(128),
            note VARCHAR(256),
            PRIMARY KEY (id),
            UNIQUE (module, operation)
        )
    """)
    op.create_index("ix_sync_meta_module", "sync_meta", ["module"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sync_meta_module", table_name="sync_meta")
    op.execute("DROP TABLE sync_meta")
