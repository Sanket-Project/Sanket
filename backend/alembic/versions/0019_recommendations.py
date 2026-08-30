"""Add recommendations — the persisted decision ledger behind the ROI dashboard.

Every decision the engine surfaces is written here at generation time with a
frozen copy of its inputs and the spreadsheet baseline it is measured against,
so realized savings can be traced back to a specific order on a specific date
rather than recomputed (and silently rewritten) from today's data.

Tenant-isolated via FORCE RLS like every other tenant-scoped table.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "industry",
            postgresql.ENUM(name="industry_code", create_type=False),
            nullable=False,
        ),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Stored as text + CHECK rather than a PG enum: the decision taxonomy is
        # product surface area that will grow, and adding a value to a CHECK is
        # a one-line migration where adding one to an enum type is not.
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("urgency", sa.Text(), nullable=False, server_default="normal"),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("recommended_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("baseline_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_units", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "confidence_band", sa.Text(), nullable=False, server_default="insufficient"
        ),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
        sa.Column(
            "reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "economics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "inputs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("linked_alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "kind IN ('purchase_order', 'excess_stock', 'safety_stock_update')",
            name="ck_recommendations_kind",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'accepted', 'dismissed', 'expired')",
            name="ck_recommendations_status",
        ),
        sa.CheckConstraint(
            "urgency IN ('critical', 'high', 'normal', 'low')",
            name="ck_recommendations_urgency",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name="ck_recommendations_confidence"
        ),
    )

    op.create_index(
        "ix_recommendations_tenant_status", "recommendations", ["tenant_id", "status"]
    )
    op.create_index("ix_recommendations_tenant_sku", "recommendations", ["tenant_id", "sku_id"])
    op.create_index(
        "ix_recommendations_decided_at", "recommendations", ["tenant_id", "decided_at"]
    )
    # One live recommendation per (sku, kind): regenerating supersedes rather
    # than stacking duplicates in the planner's queue.
    op.execute(
        "CREATE UNIQUE INDEX uq_recommendations_open_per_sku_kind "
        "ON recommendations (tenant_id, sku_id, kind) WHERE status = 'open'"
    )

    op.execute(
        "CREATE TRIGGER trg_recommendations_updated_at "
        "BEFORE UPDATE ON recommendations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.execute("ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY recommendations_isolation ON recommendations "
        "USING (bypass_rls() OR tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON recommendations TO sanket_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS recommendations_isolation ON recommendations")
    op.execute("DROP TRIGGER IF EXISTS trg_recommendations_updated_at ON recommendations")
    op.execute("DROP INDEX IF EXISTS uq_recommendations_open_per_sku_kind")
    op.drop_index("ix_recommendations_decided_at", table_name="recommendations")
    op.drop_index("ix_recommendations_tenant_sku", table_name="recommendations")
    op.drop_index("ix_recommendations_tenant_status", table_name="recommendations")
    op.drop_table("recommendations")
