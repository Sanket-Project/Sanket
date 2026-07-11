"""Grant SELECT on alembic_version to the least-privilege app role.

Background
----------
0011 introduced ``sanket_app`` as a NOSUPERUSER / NOBYPASSRLS runtime role and
granted it only the table privileges it needs. ``alembic_version`` was never in
that list, so the startup migration-drift check
(``Database.check_migrations`` → ``SELECT version_num FROM alembic_version``)
raised ``InsufficientPrivilegeError`` when the app connects as ``sanket_app``.
The check swallows the error and returns ``True`` ("assume OK"), which silently
defeats the guard — the app would happily boot against an un-migrated schema.

Granting read on this one bookkeeping table restores the check without loosening
tenant isolation (``alembic_version`` holds no tenant data and is never written
by the app role). Must run as the table owner (``postgres``) — set
``MIGRATION_DATABASE_URL`` to a privileged role when applying migrations.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Guard the role reference so the migration is a no-op on stacks that never
# created the least-privilege role (e.g. some local/test setups run as owner).
_GRANT = """
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
        GRANT SELECT ON alembic_version TO sanket_app;
    END IF;
END
$grant$;
"""

_REVOKE = """
DO $revoke$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
        REVOKE SELECT ON alembic_version FROM sanket_app;
    END IF;
END
$revoke$;
"""


def upgrade() -> None:
    op.execute(_GRANT)


def downgrade() -> None:
    op.execute(_REVOKE)
