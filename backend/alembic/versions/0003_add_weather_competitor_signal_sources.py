"""Add weather and competitor_price to trend_signal_source enum.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-29
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("weather", "competitor_price")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(
            f"ALTER TYPE trend_signal_source ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    pass
