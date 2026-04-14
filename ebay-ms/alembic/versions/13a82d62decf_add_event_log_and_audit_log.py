"""add event_log and audit_log

Revision ID: 13a82d62decf
Revises: dde7060d7740
Create Date: 2026-04-14 22:55:44.733894

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '13a82d62decf'
down_revision: Union[str, Sequence[str], None] = 'dde7060d7740'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'event_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'DONE', 'FAILED', 'DEAD_LETTER', name='eventstatus'), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('handler_name', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_event_log_event_type', 'event_log', ['event_type'], unique=False)
    op.create_index('ix_event_log_status', 'event_log', ['status'], unique=False)

    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('operator', sa.String(length=128), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_action', 'audit_log', ['action'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index('ix_event_log_status', table_name='event_log')
    op.drop_index('ix_event_log_event_type', table_name='event_log')
    op.drop_table('event_log')
