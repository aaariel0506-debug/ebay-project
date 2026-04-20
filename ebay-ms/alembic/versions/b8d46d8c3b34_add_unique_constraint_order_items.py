"""add unique constraint on order_items (order_id, sku)

Revision ID: b8d46d8c3b34
Revises: 82b6ba3706c4
Create Date: 2026-04-21 07:52:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b8d46d8c3b34"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "82b6ba3706c4"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("order_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_order_items_order_sku", ["order_id", "sku"]
        )


def downgrade() -> None:
    with op.batch_alter_table("order_items") as batch_op:
        batch_op.drop_constraint("uq_order_items_order_sku", type_="unique")
