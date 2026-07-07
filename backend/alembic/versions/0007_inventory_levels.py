"""Add inventory_levels — real warehouse stock feed for the insight layer.

Shortage alerts, coverage-days, replenishment, and financial risk previously
had no inventory source and fell back to a fabricated `safety_stock * 2`. This
table holds the current on-hand position per (tenant, sku, location) so those
insights reflect actual warehouse stock against forecast demand.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_levels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "industry",
            postgresql.ENUM(name="industry_code", create_type=False),
            nullable=False,
        ),
        sa.Column("location", sa.Text(), nullable=False, server_default="default"),
        sa.Column("on_hand_units", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("inbound_units", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reserved_units", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.CheckConstraint("on_hand_units >= 0", name="ck_inventory_on_hand_nonneg"),
        sa.CheckConstraint("inbound_units >= 0", name="ck_inventory_inbound_nonneg"),
        sa.CheckConstraint("reserved_units >= 0", name="ck_inventory_reserved_nonneg"),
        sa.UniqueConstraint("tenant_id", "sku_id", "location", name="uq_inventory_tenant_sku_loc"),
    )
    op.create_index("idx_inventory_tenant_sku", "inventory_levels", ["tenant_id", "sku_id"])
    op.create_index("idx_inventory_tenant_industry", "inventory_levels", ["tenant_id", "industry"])

    op.execute(
        "CREATE TRIGGER trg_inventory_levels_updated_at "
        "BEFORE UPDATE ON inventory_levels "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.execute("ALTER TABLE inventory_levels ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY inventory_levels_isolation ON inventory_levels "
        "USING (tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON inventory_levels TO sanket_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS inventory_levels_isolation ON inventory_levels")
    op.drop_index("idx_inventory_tenant_industry", table_name="inventory_levels")
    op.drop_index("idx_inventory_tenant_sku", table_name="inventory_levels")
    op.drop_table("inventory_levels")
