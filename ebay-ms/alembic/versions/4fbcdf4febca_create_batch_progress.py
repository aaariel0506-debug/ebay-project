"""create_batch_progress

Revision ID: 4fbcdf4febca
Revises: e617403b1604
Create Date: 2026-04-15 13:52:03.982533

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4fbcdf4febca'
down_revision: Union[str, Sequence[str], None] = 'e617403b1604'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('batch_progress',
    sa.Column('batch_id', sa.String(length=64), nullable=False),
    sa.Column('last_row', sa.Integer(), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('batch_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('batch_progress')
