"""Add rss, pinterest, tiktok, instagram to trend_signal_source enum.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-26
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# PostgreSQL ALTER TYPE … ADD VALUE is irreversible within a transaction, so
# we use IF NOT EXISTS for idempotency.  Downgrade is intentionally a no-op:
# removing enum values would require a full type rebuild and all dependant
# column re-casts which is unsafe for a running system.

_NEW_VALUES = ("rss", "pinterest", "tiktok", "instagram")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(
            f"ALTER TYPE trend_signal_source ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # Enum value removal is not safely reversible in PostgreSQL.
    # To roll back, rebuild the type manually after migrating all rows.
    pass
