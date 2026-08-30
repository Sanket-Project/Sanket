"""Seed the least-privilege account used by the public sandbox CTA.

Existing databases already contained the ``sanket-dev`` tenant when the
sandbox account was added, so the startup seed's old early return never created
the user.  ``POST /auth/sandbox-session`` consequently returned 401 forever.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO users (
            id, tenant_id, email, password_hash, full_name,
            role, active_industry, is_active
        )
        SELECT
            gen_random_uuid(), id, 'sandbox@sanket-dev.com', NULL,
            'Sandbox Guest', 'viewer', active_industry, TRUE
        FROM tenants
        WHERE slug = 'sanket-dev'
        ON CONFLICT (tenant_id, email) DO UPDATE
        SET password_hash = NULL,
            full_name = 'Sandbox Guest',
            role = 'viewer',
            is_active = TRUE,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM users
        WHERE email = 'sandbox@sanket-dev.com'
          AND tenant_id = (SELECT id FROM tenants WHERE slug = 'sanket-dev')
        """
    )
