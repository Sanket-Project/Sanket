"""Seed the agrocenter + hardware industry definitions.

These rows reference the ``industry_code`` enum labels added in 0011. They live
in a separate migration because Postgres forbids using a freshly-added enum
value in the same transaction it was created in; with
``transaction_per_migration=True`` (see ``alembic/env.py``) 0011 has committed
by the time this runs.

The replayed files (``sql/007_agrocenter.sql`` / ``sql/008_hardware.sql``) are
idempotent (``ON CONFLICT`` everywhere) and self-guard their dev-tenant catalog
seeding (``IF v_tenant_id IS NULL THEN RETURN``), so they are safe on both fresh
production databases (no dev tenant → only the ``industries`` definition row is
written) and existing dev stacks. We strip the leading ``ALTER TYPE ... ADD
VALUE`` statement from each — the enum was already extended in 0011, and issuing
``ADD VALUE`` here would be redundant.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-13
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

# Matches the "ALTER TYPE industry_code ADD VALUE ... 'x';" line (the only
# statement in these files that is not transaction-safe / already applied).
_ADD_VALUE_RE = re.compile(
    r"^\s*ALTER\s+TYPE\s+industry_code\s+ADD\s+VALUE.*?;\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _read_without_add_value(name: str) -> str:
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    return _ADD_VALUE_RE.sub("", path.read_text(encoding="utf-8"))


def _seed_if_missing(industry_code: str, sql_file: str) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM industries WHERE code = :c"), {"c": industry_code}
    ).scalar()
    if exists is None:
        from app.core.sql_replay import exec_sql_script

        exec_sql_script(_read_without_add_value(sql_file))


def upgrade() -> None:
    _seed_if_missing("agrocenter", "007_agrocenter.sql")
    _seed_if_missing("hardware", "008_b_hardware.sql")


def downgrade() -> None:
    # Industry definition rows are reference data; leaving them in place is
    # harmless and dropping enum labels is not supported by Postgres.
    pass
