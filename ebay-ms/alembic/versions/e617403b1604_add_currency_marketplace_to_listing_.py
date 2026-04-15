"""add_currency_marketplace_to_listing_templates

Revision ID: e617403b1604
Revises: 37c8515b5725
Create Date: 2026-04-15 13:46:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e617403b1604'
down_revision: Union[str, Sequence[str], None] = '37c8515b5725'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add currency and marketplace_id columns to listing_templates (SQLite compatible)."""
    # SQLite: add column as nullable, application sets defaults
    op.add_column(
        'listing_templates',
        sa.Column('currency', sa.String(length=3), nullable=True),
    )
    op.add_column(
        'listing_templates',
        sa.Column('marketplace_id', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('listing_templates', 'marketplace_id')
    op.drop_column('listing_templates', 'currency')
