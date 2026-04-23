"""add total_due_seller_raw and sold_via_ad_campaign to orders

Revision ID: bbb222222222
Revises: 1f2e3d4c5b6a
Create Date: 2026-04-24 00:43:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bbb222222222'  # pragma: allowlist secret
down_revision: Union[str, None] = '1f2e3d4c5b6a'  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("total_due_seller_raw", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("sold_via_ad_campaign", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("sold_via_ad_campaign")
        batch_op.drop_column("total_due_seller_raw")
