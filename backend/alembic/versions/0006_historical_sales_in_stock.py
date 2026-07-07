"""Add nullable in_stock availability flag to historical_sales.

Powers the ML censored-demand (lost-sales) correction: a stockout produces a
zero-sales period that does not mean demand was zero. Recording availability
lets the forecaster unconstrain that demand instead of learning a false drop.

Nullable by design — existing rows and feeds without an availability signal
stay NULL, which the correction interprets as "unknown / assume in stock".

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: present in the baseline snapshot (sql/002) on a fresh chain.
    op.execute("ALTER TABLE historical_sales ADD COLUMN IF NOT EXISTS in_stock BOOLEAN")


def downgrade() -> None:
    op.drop_column("historical_sales", "in_stock")
