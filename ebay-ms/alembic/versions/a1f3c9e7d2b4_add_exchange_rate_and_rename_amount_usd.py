"""add exchange_rates and rename amount_usd to amount_jpy

Revision ID: a1f3c9e7d2b4
Revises: b8d46d8c3b34
Create Date: 2026-04-22 18:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f3c9e7d2b4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b8d46d8c3b34"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column("amount_usd", new_column_name="amount_jpy")

    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("from_currency", sa.String(length=3), nullable=False),
        sa.Column("to_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="csv"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("rate_date", "from_currency", "to_currency", name="uq_exchange_rates_date_pair"),
    )
    op.create_index("ix_exchange_rates_rate_date", "exchange_rates", ["rate_date"])
    op.create_index(
        "ix_exchange_rates_currencies",
        "exchange_rates",
        ["rate_date", "from_currency", "to_currency"],
    )


def downgrade() -> None:
    op.drop_index("ix_exchange_rates_currencies", table_name="exchange_rates")
    op.drop_index("ix_exchange_rates_rate_date", table_name="exchange_rates")
    op.drop_table("exchange_rates")

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column("amount_jpy", new_column_name="amount_usd")
