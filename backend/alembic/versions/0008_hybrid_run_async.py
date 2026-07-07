"""Make hybrid_forecast_runs an async job record.

The hybrid forecast now runs out-of-process (arq worker) because Chronos
inference can take ~60s+ — longer than client/proxy timeouts allow for a
synchronous request. The run row is created up-front (status=pending) and
driven through running → completed/failed by the worker, with the full
HybridForecastOut payload stored in `result` so pollers and history can read
it back without recomputing.

The previously-NOT NULL compute columns (trend_score, signal_volatility,
alpha, beta) become nullable since they're unknown until the job finishes.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: the phase-6 baseline snapshot (sql/006) predates these async
    # columns, so they are genuinely added here — but guard with IF NOT EXISTS so
    # the migration is also safe on a database that already has them.
    op.execute(
        "ALTER TABLE hybrid_forecast_runs "
        "ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE hybrid_forecast_runs "
        "ADD COLUMN IF NOT EXISTS request_params JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute("ALTER TABLE hybrid_forecast_runs ADD COLUMN IF NOT EXISTS result JSONB")
    op.execute("ALTER TABLE hybrid_forecast_runs ADD COLUMN IF NOT EXISTS error TEXT")
    op.execute(
        "ALTER TABLE hybrid_forecast_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
    )

    # Compute columns are unknown until the job completes (DROP NOT NULL is a
    # no-op when already nullable).
    for col in ("trend_score", "signal_volatility", "alpha", "beta"):
        op.execute(f"ALTER TABLE hybrid_forecast_runs ALTER COLUMN {col} DROP NOT NULL")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hybrid_runs_tenant_status "
        "ON hybrid_forecast_runs (tenant_id, status)"
    )

    # Backfill: any pre-existing rows were synchronous successes.
    op.execute("UPDATE hybrid_forecast_runs SET status = 'completed' WHERE status = 'pending'")


def downgrade() -> None:
    op.drop_index("idx_hybrid_runs_tenant_status", table_name="hybrid_forecast_runs")
    for col in ("beta", "alpha", "signal_volatility", "trend_score"):
        op.alter_column("hybrid_forecast_runs", col, nullable=False)
    op.drop_column("hybrid_forecast_runs", "completed_at")
    op.drop_column("hybrid_forecast_runs", "error")
    op.drop_column("hybrid_forecast_runs", "result")
    op.drop_column("hybrid_forecast_runs", "request_params")
    op.drop_column("hybrid_forecast_runs", "status")
