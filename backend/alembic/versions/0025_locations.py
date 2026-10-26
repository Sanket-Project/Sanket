"""Add locations — the store / warehouse network of a tenant (location spec §3).

Sales and inventory keep their free-text ``location``; rows resolve to a
location by ``code = lower(trim(location))``. Kind is text + CHECK (as in
recommendations) so adding a kind is a one-line migration.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="unconfirmed"),
        sa.Column("parent_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lead_time_days_from_parent", sa.SmallInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("attributes", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_locations_tenant_code"),
        sa.CheckConstraint("kind IN ('warehouse', 'store', 'unconfirmed')",
                           name="ck_locations_kind"),
        sa.CheckConstraint("code = lower(btrim(code)) AND code NOT IN ('', 'default')",
                           name="ck_locations_code_normalised"),
        sa.CheckConstraint("lead_time_days_from_parent IS NULL OR lead_time_days_from_parent >= 0",
                           name="ck_locations_lead_time"),
    )
    op.execute(
        "CREATE TRIGGER trg_locations_updated_at BEFORE UPDATE ON locations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE locations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE locations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY locations_isolation ON locations "
        "USING (bypass_rls() OR tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON locations TO sanket_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS locations_isolation ON locations")
    op.execute("DROP TRIGGER IF EXISTS trg_locations_updated_at ON locations")
    op.drop_table("locations")
