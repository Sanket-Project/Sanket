"""Add invites — pending team-member invitations for onboarding's team step.

Stores outstanding invites per tenant with a target role and a one-time token
hash. Tenant-isolated via RLS like every other tenant-scoped table.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    invite_status = postgresql.ENUM(
        "pending", "accepted", "revoked", "expired", name="invite_status"
    )
    invite_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "invites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        # Reuse the existing user_role enum type (created in the baseline).
        sa.Column(
            "role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="invite_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
    )
    op.create_index("idx_invites_tenant_status", "invites", ["tenant_id", "status"])

    op.execute(
        "CREATE TRIGGER trg_invites_updated_at "
        "BEFORE UPDATE ON invites "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.execute("ALTER TABLE invites ENABLE ROW LEVEL SECURITY")
    # FORCE so the table owner is also subject to the policy. Without it a role
    # that owns the table bypasses tenant isolation entirely — the exact gap the
    # test_force_rls_enabled_on_all_tenant_tables guard catches, and how earlier
    # tables were hardened in migration 0011.
    op.execute("ALTER TABLE invites FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY invites_isolation ON invites "
        "USING (bypass_rls() OR tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON invites TO sanket_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS invites_isolation ON invites")
    op.execute("DROP TRIGGER IF EXISTS trg_invites_updated_at ON invites")
    op.drop_index("idx_invites_tenant_status", table_name="invites")
    op.drop_table("invites")
    postgresql.ENUM(name="invite_status").drop(op.get_bind(), checkfirst=True)
