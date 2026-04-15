"""Create stocktakes and stocktake_items tables

Revision ID: 27e8b3f6c1d0  # pragma: allowlist secret
Revises: 36f52c04f1b9  # pragma: allowlist secret
Create Date: 2026-04-16 07:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "27e8b3f6c1d0"  # pragma: allowlist secret
down_revision = "36f52c04f1b9"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stocktakes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "status",
            sa.Enum("in_progress", "finished", "cancelled", name="stocktakestatus"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stocktakes_status", "stocktakes", ["status"])

    op.create_table(
        "stocktake_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "stocktake_id",
            sa.Integer(),
            sa.ForeignKey("stocktakes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sku",
            sa.String(length=64),
            sa.ForeignKey("products.sku"),
            nullable=False,
        ),
        sa.Column("system_quantity", sa.Integer(), nullable=False),
        sa.Column("actual_quantity", sa.Integer(), nullable=True),
        sa.Column("difference", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stocktake_items_stocktake_id", "stocktake_items", ["stocktake_id"])
    op.create_index("ix_stocktake_items_sku", "stocktake_items", ["sku"])


def downgrade() -> None:
    op.drop_index("ix_stocktake_items_sku")
    op.drop_index("ix_stocktake_items_stocktake_id")
    op.drop_table("stocktake_items")
    op.drop_index("ix_stocktakes_status")
    op.drop_table("stocktakes")
    op.execute("DROP TYPE IF EXISTS stocktakestatus")
