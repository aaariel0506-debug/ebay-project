"""add ad_fee_total and buyer_paid_total to orders

Revision ID: 1f2e3d4c5b6a
Revises: a1f3c9e7d2b4
Create Date: 2026-04-23

"""
import sqlalchemy as sa
from alembic import op

revision = "1f2e3d4c5b6a"  # pragma: allowlist secret
down_revision = "a1f3c9e7d2b4"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("ad_fee_total", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("buyer_paid_total", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("buyer_paid_total")
        batch_op.drop_column("ad_fee_total")
