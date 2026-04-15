"""create_supplier_price_history

Revision ID: 102cfcaae272
Revises: 3ba56797d01a
Create Date: 2026-04-15 18:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '102cfcaae272'
down_revision: Union[str, Sequence[str], None] = '4fbcdf4febca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add supplier_price_history table."""
    op.create_table(
        'supplier_price_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('supplier', sa.String(length=128), nullable=True),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('recorded_at', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sku'], ['products.sku'], ondelete='CASCADE'),
    )
    op.create_index('ix_supplier_price_history_sku', 'supplier_price_history', ['sku'])
    op.create_index('ix_supplier_price_history_recorded_at', 'supplier_price_history', ['recorded_at'])
    op.create_index('ix_supplier_price_history_sku_recorded', 'supplier_price_history', ['sku', 'recorded_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('supplier_price_history')
