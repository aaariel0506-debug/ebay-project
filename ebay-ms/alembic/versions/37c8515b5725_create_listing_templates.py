"""create_listing_templates

Revision ID: 37c8515b5725
Revises: 3ba56797d01a
Create Date: 2026-04-15 11:13:59.736533

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '37c8515b5725'
down_revision: Union[str, Sequence[str], None] = '3ba56797d01a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('listing_templates',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description_template', sa.Text(), nullable=True),
    sa.Column('category_id', sa.String(length=50), nullable=True),
    sa.Column('condition', sa.String(length=30), nullable=True),
    sa.Column('condition_description', sa.Text(), nullable=True),
    sa.Column('shipping_policy_id', sa.String(length=100), nullable=True),
    sa.Column('return_policy_id', sa.String(length=100), nullable=True),
    sa.Column('payment_policy_id', sa.String(length=100), nullable=True),
    sa.Column('default_price_markup', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('image_settings', sa.JSON(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_listing_templates_name'), 'listing_templates', ['name'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_listing_templates_name'), table_name='listing_templates')
    op.drop_table('listing_templates')
