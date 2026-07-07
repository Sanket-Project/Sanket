"""Baseline migration — applies sql/001_extensions.sql + 002_schema.sql + 003_rls_policies.sql

Future migrations should use op.add_column / op.create_table directly; this
revision exists so that fresh databases can be brought up entirely via Alembic
(`alembic upgrade head`) without requiring operators to run raw .sql files.

Revision ID: 0001
Revises:
Create Date: 2026-05-25
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def _exec_file(name: str) -> None:
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    sql = path.read_text(encoding="utf-8")
    # asyncpg uses the prepared-statement protocol, which rejects multi-command
    # strings, so the script is split and executed one statement at a time.
    from app.core.sql_replay import exec_sql_script

    exec_sql_script(sql)


def upgrade() -> None:
    _exec_file("001_extensions.sql")
    _exec_file("002_schema.sql")
    _exec_file("003_rls_policies.sql")
    # Phase-5 (billing/realtime) and phase-6 (trends/alerts) schema must be part
    # of the baseline: later migrations alter the enums/tables they define
    # (0002/0003/0009 extend trend_signal_source, 0008 alters
    # hybrid_forecast_runs, 0010 renames subscription columns). They were
    # previously only created by the docker-compose initdb step, so a standalone
    # `alembic upgrade head` failed. Creating them here makes the chain runnable
    # end-to-end. The 0011 reconciliation is sentinel-guarded, so it becomes a
    # no-op for these on any database the baseline already built.
    _exec_file("005_phase5_realtime_billing.sql")
    _exec_file("006_phase6_trends_alerts.sql")
    # Seed data is run separately so prod environments can opt-out.
    # _exec_file("004_seed.sql")


def downgrade() -> None:
    op.execute(
        """
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
            FOR r IN (SELECT typname FROM pg_type WHERE typnamespace =
                      (SELECT oid FROM pg_namespace WHERE nspname='public') AND typtype = 'e')
            LOOP
                EXECUTE 'DROP TYPE IF EXISTS public.' || quote_ident(r.typname) || ' CASCADE';
            END LOOP;
        END $$;
        """
    )
