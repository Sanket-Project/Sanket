"""Reconcile the schema and harden tenant isolation.

Two problems are fixed here so that a fresh production database built purely
with ``alembic upgrade head`` is complete **and** tenant-isolated:

1. **Incomplete migration chain.** The baseline (0001) only replayed
   ``sql/001-003``. The phase-5 billing/realtime tables (``sql/005``), the
   phase-6 trend/alert tables (``sql/006``), and the integration table
   (``sql/009``) were only ever created by the docker-compose ``initdb`` step,
   never by Alembic — so ``alembic upgrade head`` produced a half-built database
   missing subscriptions, usage metering, trends, alerts and integrations. We
   replay those files here, guarded by an existence check so the migration is a
   no-op on databases that already have them (e.g. existing dev stacks).

2. **RLS was not actually enforced.** Row-level security relies on the
   application connecting as a role that is neither superuser nor the table
   owner — *and* on ``FORCE ROW LEVEL SECURITY`` so the owner is subject to the
   policies too. Neither was guaranteed. We:
     * add RLS + an isolation policy to the four analytics tables created in
       migration 0004 (``pos_ingest``, ``forecast_accuracy_metrics``,
       ``supplier_lead_time_log``, ``data_quality_issues``) which had none, and
     * ``FORCE ROW LEVEL SECURITY`` on **every** table that has RLS enabled,
       so the policies hold even when the connection role owns the table.

   The companion least-privilege role hardening lives in ``sql/003`` and the
   deployment manifests (the app must connect as ``sanket_app``, which is
   ``NOSUPERUSER NOBYPASSRLS``).

Enum extension for the agrocenter/hardware verticals is added here (commit-safe
in PG12+) and the rows that *use* those labels are seeded in 0012, because
Postgres forbids using a freshly-added enum value in the same transaction.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-13
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

# Tenant tables created in migration 0004 that shipped with NO row-level
# security — a cross-tenant data-leak hole.
_ORPHAN_RLS_TABLES = (
    "pos_ingest",
    "forecast_accuracy_metrics",
    "supplier_lead_time_log",
    "data_quality_issues",
)


def _read_sql(name: str) -> str:
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    return path.read_text(encoding="utf-8")


def _exec_if_missing(sentinel_table: str, sql_file: str) -> None:
    """Replay ``sql_file`` (as top-level multi-statement SQL) only when
    ``sentinel_table`` does not yet exist.

    The phase-5/6/9 SQL files use non-idempotent DDL (``CREATE TYPE`` /
    ``CREATE TRIGGER`` without ``IF NOT EXISTS``) and contain their own
    ``DO``/partition blocks, so we cannot wrap them in a guard block. Instead we
    gate the whole file in Python on a single representative table — a no-op on
    databases that already have it (existing dev stacks), a full create on a
    fresh ``alembic upgrade head`` production database.
    """
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT to_regclass(:t)"), {"t": f"public.{sentinel_table}"}
    ).scalar()
    if exists is None:
        from app.core.sql_replay import exec_sql_script

        exec_sql_script(_read_sql(sql_file))


def upgrade() -> None:
    # ── 1. Extend the industry enum (commit-safe; values used in 0012) ───────
    op.execute("ALTER TYPE industry_code ADD VALUE IF NOT EXISTS 'agrocenter'")
    op.execute("ALTER TYPE industry_code ADD VALUE IF NOT EXISTS 'hardware'")

    # ── 2. Replay the orphaned schema files (idempotent via sentinel guard) ──
    # NOTE: sql/008_inventory.sql is intentionally skipped — inventory_levels is
    # already created by migration 0007.
    _exec_if_missing("subscriptions", "005_phase5_realtime_billing.sql")
    _exec_if_missing("trend_signals", "006_phase6_trends_alerts.sql")
    _exec_if_missing("integration_connections", "009_integrations.sql")

    # ── 3. Close the RLS gap on the migration-0004 analytics tables ──────────
    for table in _ORPHAN_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            DO $pol$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public'
                      AND tablename = '{table}'
                      AND policyname = '{table}_isolation'
                ) THEN
                    EXECUTE 'CREATE POLICY {table}_isolation ON {table} '
                            'USING (tenant_id = current_tenant_id()) '
                            'WITH CHECK (tenant_id = current_tenant_id())';
                END IF;
            END
            $pol$;
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO sanket_app")

    # data_quality_issues allows tenant_id IS NULL (platform-level issues); relax
    # its policy so those rows remain insertable/visible to the owning context.
    op.execute("DROP POLICY IF EXISTS data_quality_issues_isolation ON data_quality_issues")
    op.execute(
        """
        CREATE POLICY data_quality_issues_isolation ON data_quality_issues
            USING (tenant_id IS NULL OR tenant_id = current_tenant_id())
            WITH CHECK (tenant_id IS NULL OR tenant_id = current_tenant_id())
        """
    )

    # ── 4. FORCE RLS on every RLS-enabled table so the owner is bound too ────
    # Without FORCE, a connection role that owns the table bypasses every policy
    # — silently defeating multi-tenant isolation.
    op.execute(
        """
        DO $force$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                  AND c.relrowsecurity = true
                  AND c.relforcerowsecurity = false
            LOOP
                EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', r.relname);
            END LOOP;
        END
        $force$;
        """
    )


def downgrade() -> None:
    # Lift FORCE RLS (policies + tables themselves are left in place; dropping
    # the replayed schema would be destructive and is intentionally not done).
    op.execute(
        """
        DO $unforce$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND c.relforcerowsecurity = true
            LOOP
                EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', r.relname);
            END LOOP;
        END
        $unforce$;
        """
    )
    for table in _ORPHAN_RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
