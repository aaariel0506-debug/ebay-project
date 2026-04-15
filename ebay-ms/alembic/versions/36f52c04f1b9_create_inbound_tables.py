"""Create inbound_receipts and inbound_receipt_items tables

Revision ID: 36f52c04f1b9  # pragma: allowlist secret
Revises: 102cfcaae272  # pragma: allowlist secret
Create Date: 2026-04-16 04:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "36f52c04f1b9"  # pragma: allowlist secret
down_revision = "102cfcaae272"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("receipt_no", sa.String(length=32), nullable=False),
        sa.Column("supplier", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "shipped", "partial", "received", "cancelled", name="inboundstatus"),
            nullable=False,
        ),
        sa.Column("expected_date", sa.DateTime(), nullable=True),
        sa.Column("received_date", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("operator", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_no"),
    )
    op.create_index("ix_inbound_receipts_receipt_no", "inbound_receipts", ["receipt_no"], unique=True)
    op.create_index("ix_inbound_receipts_supplier", "inbound_receipts", ["supplier"])
    op.create_index("ix_inbound_receipts_status", "inbound_receipts", ["status"])

    op.create_table(
        "inbound_receipt_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("inbound_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(length=64), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("expected_quantity", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbound_items_receipt_id", "inbound_receipt_items", ["receipt_id"])
    op.create_index("ix_inbound_items_sku", "inbound_receipt_items", ["sku"])
    op.create_index("ix_inbound_items_receipt_sku", "inbound_receipt_items", ["receipt_id", "sku"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_inbound_items_receipt_sku")
    op.drop_index("ix_inbound_items_sku")
    op.drop_index("ix_inbound_items_receipt_id")
    op.drop_table("inbound_receipt_items")
    op.drop_index("ix_inbound_receipts_status")
    op.drop_index("ix_inbound_receipts_supplier")
    op.drop_index("ix_inbound_receipts_receipt_no")
    op.drop_table("inbound_receipts")
    op.execute("DROP TYPE IF EXISTS inboundstatus")
