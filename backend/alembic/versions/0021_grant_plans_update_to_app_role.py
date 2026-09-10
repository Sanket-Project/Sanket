"""Grant UPDATE on plans to sanket_app role for plan synchronization.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GRANT = """
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
        GRANT UPDATE (razorpay_plan_id) ON plans TO sanket_app;
    END IF;
END
$grant$;
"""

_REVOKE = """
DO $revoke$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
        REVOKE UPDATE ON plans FROM sanket_app;
    END IF;
END
$revoke$;
"""


def upgrade() -> None:
    op.execute(_GRANT)


def downgrade() -> None:
    op.execute(_REVOKE)
