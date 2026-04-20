"""split order line_items into OrderItem table

Revision ID: 82b6ba3706c4
Revises: 6e3d8f2a1c4d
Create Date: 2026-04-20 23:25:36.810718

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "82b6ba3706c4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "6e3d8f2a1c4d"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 OrderItem 子表，数据迁移，然后从 Order 表删除 sku 字段。"""

    # ── 1. 创建 order_items 表 ─────────────────────────────────────────
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("sale_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.ebay_order_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku"], ["products.sku"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"], unique=False)
    op.create_index("ix_order_items_sku", "order_items", ["sku"], unique=False)

    # ── 2. 数据迁移 ───────────────────────────────────────────────────
    # 把 Order 现有的 (sku, sale_price) 迁成 OrderItem
    # quantity=1, unit_price=sale_price 作为占位（历史数据精确值 Day 34 修正）
    op.execute("""
        INSERT INTO order_items (order_id, sku, quantity, unit_price, sale_amount, created_at, updated_at)
        SELECT
            ebay_order_id,
            sku,
            1,
            sale_price,
            sale_price,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM orders
        WHERE sku IS NOT NULL AND sku != ''
    """)

    # ── 3. 删除 orders.sku 列（SQLite rename-and-copy 方式）──────────────
    # SQLite 不支持 DROP COLUMN，使用 CREATE TABLE ... AS ... 方式
    op.execute("PRAGMA foreign_keys=off")
    # 删索引（如果存在）
    op.execute("DROP INDEX IF EXISTS ix_orders_sku")
    # 创建新表（不含 sku）
    op.execute("""
        CREATE TABLE orders_new AS
        SELECT
            ebay_order_id,
            sale_price,
            shipping_cost,
            ebay_fee,
            buyer_country,
            status,
            order_date,
            ship_date,
            buyer_name,
            shipping_address,
            created_at,
            updated_at
        FROM orders
    """)
    op.execute("DROP TABLE orders")
    op.execute("ALTER TABLE orders_new RENAME TO orders")
    op.execute("PRAGMA foreign_keys=on")


def downgrade() -> None:
    """从 OrderItem 恢复数据到 Order.sku，然后删除 OrderItem 表。"""

    # ── 1. 恢复 orders.sku 列 ─────────────────────────────────────────
    # 先重建带 sku 的 orders 表
    op.execute("PRAGMA foreign_keys=off")
    op.execute("""
        CREATE TABLE orders_old AS
        SELECT
            ebay_order_id,
            sale_price,
            shipping_cost,
            ebay_fee,
            buyer_country,
            status,
            order_date,
            ship_date,
            buyer_name,
            shipping_address,
            created_at,
            updated_at
        FROM orders
    """)
    op.execute("DROP TABLE orders")
    op.execute("""
        CREATE TABLE orders (
            ebay_order_id VARCHAR(64) NOT NULL,
            sku VARCHAR(64) NOT NULL,
            sale_price NUMERIC(12, 2) NOT NULL,
            shipping_cost NUMERIC(12, 2) NOT NULL,
            ebay_fee NUMERIC(12, 2) NOT NULL,
            buyer_country VARCHAR(3),
            status VARCHAR(9) NOT NULL,
            order_date DATETIME,
            ship_date DATETIME,
            buyer_name VARCHAR(256),
            shipping_address VARCHAR(512),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (ebay_order_id)
        )
    """)
    # 从 order_items 回填 sku（每个 order 取第一条）
    op.execute("""
        UPDATE orders SET sku = (
            SELECT sku FROM order_items
            WHERE order_id = orders.ebay_order_id
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM order_items
            WHERE order_id = orders.ebay_order_id
        )
    """)
    op.execute("DROP TABLE orders_old")
    op.execute("PRAGMA foreign_keys=on")

    # ── 2. 删除 order_items 表 ─────────────────────────────────────────
    op.drop_index("ix_order_items_sku", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
