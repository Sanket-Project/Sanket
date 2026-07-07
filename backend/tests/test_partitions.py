"""Tests for automated partition maintenance + the analytics index audit.

Runs against the same testcontainers Postgres built by the real Alembic chain
(see conftest.setup_schema), so this exercises migrations 0013 (partition
functions) and 0014 (covering index) exactly as production applies them.
"""

from __future__ import annotations

import os
from datetime import date

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def engine(setup_schema):
    eng = create_async_engine(os.environ["DATABASE_URL"])
    try:
        yield eng
    finally:
        await eng.dispose()


def _current_quarter_partition(parent: str) -> str:
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    return f"{parent}_{today.year}_q{quarter}"


async def test_current_quarter_partition_exists(engine):
    """Migration 0013 runs sanket_maintain_partitions(), so the live quarter
    must have a partition regardless of the static 2022-2027 seed range."""
    part = _current_quarter_partition("historical_sales")
    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT to_regclass(:p)"), {"p": part})
    assert exists is not None, f"expected partition {part} to exist"


async def test_maintain_partitions_is_idempotent(engine):
    """The migration already extended the rolling window, so calling maintain
    again should create zero new partitions."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT parent, created FROM sanket_maintain_partitions()"))
        ).all()
        await conn.commit()
    created = {r[0]: r[1] for r in rows}
    assert created.get("historical_sales") == 0
    assert created.get("forecast_results") == 0


async def test_ensure_creates_partitions_beyond_window(engine):
    """A lookahead past the seeded/maintained window creates new partitions on
    first call and nothing on the second (idempotency)."""
    async with engine.connect() as conn:
        first = await conn.scalar(
            text("SELECT sanket_ensure_quarterly_partitions('historical_sales'::regclass, 0, 24)")
        )
        await conn.commit()
        second = await conn.scalar(
            text("SELECT sanket_ensure_quarterly_partitions('historical_sales'::regclass, 0, 24)")
        )
        await conn.commit()
    assert first > 0, "a far lookahead should create new partitions"
    assert second == 0, "re-running must be a no-op"


async def test_covering_index_present_and_old_index_dropped(engine):
    """Index audit (migration 0014): the covering index exists and the
    superseded idx_hsales_industry has been removed."""
    async with engine.connect() as conn:
        names = set(
            await conn.scalars(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'historical_sales'")
            )
        )
    assert "idx_hsales_agg_covering" in names
    assert "idx_hsales_industry" not in names


async def test_covering_index_includes_measure_columns(engine):
    """The covering index must INCLUDE the summed measures so the analytics
    aggregation can be served index-only."""
    async with engine.connect() as conn:
        indexdef = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_hsales_agg_covering'")
        )
    assert indexdef is not None
    lowered = indexdef.lower()
    assert "include" in lowered
    for col in ("units_sold", "gross_revenue", "net_revenue", "returns"):
        assert col in lowered
