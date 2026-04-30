"""add products parent_sku

Revision ID: 97cab5bb88ad
Revises: 98a7b2c3d4e5_f05
Create Date: 2026-04-30 16:22:37.695643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "97cab5bb88ad"
down_revision: Union[str, Sequence[str], None] = "98a7b2c3d4e5_f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("parent_sku", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_products_parent_sku", ["parent_sku"], unique=False)
        # SQLite FK created via REFERENCES in column def - not a separate constraint


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        # Drop the index (FK constraint auto-removed with column)
        batch_op.drop_index("ix_products_parent_sku")
        batch_op.drop_column("parent_sku")
