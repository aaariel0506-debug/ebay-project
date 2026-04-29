"""extend products for import-listings: title/cost nullable + asin + variant_note

Revision ID: 98a7b2c3d4e5_f05_add_asin_variant_note.py
Revises: c1d2e3f4a5b6
Create Date: 2026-04-29 12:30:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "98a7b2c3d4e5_f05"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend products: title/cost_price nullable + asin + variant_note."""
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column("title", existing_type=sa.String(256), nullable=True)
        batch_op.alter_column(
            "cost_price",
            existing_type=sa.Numeric(12, 2),
            nullable=True,
        )
        batch_op.add_column(sa.Column("asin", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("variant_note", sa.Text(), nullable=True))
    op.create_index("ix_products_asin", "products", ["asin"])


def downgrade() -> None:
    """Revert: drop new columns + restore NOT NULL."""
    op.drop_index("ix_products_asin", table_name="products")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("variant_note")
        batch_op.drop_column("asin")
        batch_op.alter_column("cost_price", existing_type=sa.Numeric(12, 2), nullable=False)
        batch_op.alter_column("title", existing_type=sa.String(256), nullable=False)
