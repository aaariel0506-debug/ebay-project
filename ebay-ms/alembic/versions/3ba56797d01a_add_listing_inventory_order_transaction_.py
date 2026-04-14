"""add listing inventory order transaction tables

Revision ID: 3ba56797d01a
Revises: 13a82d62decf
Create Date: 2026-04-15 00:06:36.050861

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3ba56797d01a'
down_revision: Union[str, Sequence[str], None] = '13a82d62decf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ebay_listings',
        sa.Column('ebay_item_id', sa.String(length=64), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=True),
        sa.Column('listing_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('quantity_available', sa.Integer(), nullable=False),
        sa.Column('variants', sa.JSON(), nullable=True),
        sa.Column('status', sa.Enum('ACTIVE', 'OUT_OF_STOCK', 'ENDED', 'DRAFT', name='listingstatus'), nullable=False),
        sa.Column('last_synced', sa.DateTime(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=128), nullable=True),
        sa.Column('condition', sa.String(length=32), nullable=True),
        sa.Column('image_urls', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['sku'], ['products.sku']),
        sa.PrimaryKeyConstraint('ebay_item_id')
    )
    op.create_index('ix_ebay_listings_sku', 'ebay_listings', ['sku'], unique=False)
    op.create_index('ix_ebay_listings_status', 'ebay_listings', ['status'], unique=False)

    op.create_table(
        'inventory',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('type', sa.Enum('IN', 'OUT', 'ADJUST', 'RETURN', name='inventorytype'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('related_order', sa.String(length=64), nullable=True),
        sa.Column('location', sa.String(length=128), nullable=True),
        sa.Column('operator', sa.String(length=128), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['sku'], ['products.sku']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inventory_sku', 'inventory', ['sku'], unique=False)
    op.create_index('ix_inventory_type', 'inventory', ['type'], unique=False)
    op.create_index('ix_inventory_related_order', 'inventory', ['related_order'], unique=False)

    op.create_table(
        'orders',
        sa.Column('ebay_order_id', sa.String(length=64), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('sale_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('shipping_cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('ebay_fee', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('buyer_country', sa.String(length=3), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'SHIPPED', 'CANCELLED', 'REFUNDED', name='orderstatus'), nullable=False),
        sa.Column('order_date', sa.DateTime(), nullable=True),
        sa.Column('ship_date', sa.DateTime(), nullable=True),
        sa.Column('buyer_name', sa.String(length=256), nullable=True),
        sa.Column('shipping_address', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['sku'], ['products.sku']),
        sa.PrimaryKeyConstraint('ebay_order_id')
    )
    op.create_index('ix_orders_sku', 'orders', ['sku'], unique=False)
    op.create_index('ix_orders_status', 'orders', ['status'], unique=False)

    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.String(length=64), nullable=True),
        sa.Column('sku', sa.String(length=64), nullable=True),
        sa.Column('type', sa.Enum('SALE', 'REFUND', 'FEE', 'SHIPPING', 'ADJUSTMENT', name='transactiontype'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('amount_usd', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('exchange_rate', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('date', sa.DateTime(), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('note', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.ebay_order_id']),
        sa.ForeignKeyConstraint(['sku'], ['products.sku']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transactions_order_id', 'transactions', ['order_id'], unique=False)
    op.create_index('ix_transactions_sku', 'transactions', ['sku'], unique=False)
    op.create_index('ix_transactions_type', 'transactions', ['type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_transactions_type', table_name='transactions')
    op.drop_index('ix_transactions_sku', table_name='transactions')
    op.drop_index('ix_transactions_order_id', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index('ix_orders_status', table_name='orders')
    op.drop_index('ix_orders_sku', table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_inventory_related_order', table_name='inventory')
    op.drop_index('ix_inventory_type', table_name='inventory')
    op.drop_index('ix_inventory_sku', table_name='inventory')
    op.drop_table('inventory')
    op.drop_index('ix_ebay_listings_status', table_name='ebay_listings')
    op.drop_index('ix_ebay_listings_sku', table_name='ebay_listings')
    op.drop_table('ebay_listings')
