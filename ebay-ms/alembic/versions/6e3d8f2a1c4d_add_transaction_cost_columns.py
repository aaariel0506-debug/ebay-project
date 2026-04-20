"""add_transaction_cost_columns

Revision ID: 6e3d8f2a1c4d
Revises: 27e8b3f6c1d0
Create Date: 2026-04-20 16:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e3d8f2a1c4d"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "27e8b3f6c1d0"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cost columns to transactions table for COGS/profit tracking."""
    op.add_column(
        "transactions",
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("total_cost", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("profit", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("margin", sa.Numeric(6, 4), nullable=True),
    )


def downgrade() -> None:
    """Remove cost columns."""
    op.drop_column("transactions", "margin")
    op.drop_column("transactions", "profit")
    op.drop_column("transactions", "total_cost")
    op.drop_column("transactions", "unit_cost")
