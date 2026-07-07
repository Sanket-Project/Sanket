"""Add fda and logistics to trend_signal_source enum.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-02
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("fda", "logistics")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(
            f"ALTER TYPE trend_signal_source ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    pass
