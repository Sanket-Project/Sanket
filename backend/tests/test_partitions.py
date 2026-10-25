"""Tests for automated partition maintenance + the analytics index audit.

Runs against the same testcontainers Postgres built by the real Alembic chain
(see conftest.setup_schema), so this exercises migrations 0013 (partition
functions) and 0014 (covering index) exactly as production applies them.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

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


# ── trend_signals: rolling monthly partitions (audit F05) ─────────────────────
# Signal ingestion failed in October 2026 with "no partition of relation
# trend_signals found for row": only May–August 2026 had been created.


def _month_partition(parent: str, d: date) -> str:
    return f"{parent}_{d.year}_{d.month:02d}"


async def test_current_and_next_months_have_trend_partitions(engine):
    today = date.today()
    nxt = date(today.year + (today.month // 12), today.month % 12 + 1, 1)
    async with engine.connect() as conn:
        for d in (today, nxt):
            assert await conn.scalar(
                text("SELECT to_regclass(:p)"), {"p": _month_partition("trend_signals", d)}
            ), d


async def test_monthly_partitions_cross_the_year_boundary_idempotently(engine):
    async with engine.connect() as conn:
        first = await conn.scalar(
            text("SELECT sanket_ensure_monthly_partitions('trend_signals'::regclass, 0, 1, DATE '2030-12-15')")
        )
        again = await conn.scalar(
            text("SELECT sanket_ensure_monthly_partitions('trend_signals'::regclass, 0, 1, DATE '2030-12-15')")
        )
        await conn.commit()
        assert first == 2
        assert again == 0
        for at in (
            datetime(2030, 12, 31, 23, 59, 59, 999000, tzinfo=UTC),
            datetime(2031, 1, 1, 0, 0, tzinfo=UTC),
        ):
            await conn.execute(
                text(
                    "INSERT INTO trend_signals (industry, source, kind, series_key, "
                    "normalized_score, captured_at) VALUES ('fashion', 'google_trends', "
                    "'search_interest', 'test:boundary', 0, :at)"
                ),
                {"at": at},
            )
        parts = (
            await conn.execute(
                text(
                    "SELECT tableoid::regclass::text FROM trend_signals "
                    "WHERE series_key = 'test:boundary' ORDER BY captured_at"
                )
            )
        ).scalars().all()
        await conn.rollback()
    assert parts == ["trend_signals_2030_12", "trend_signals_2031_01"]


async def test_maintenance_covers_trend_signals(engine):
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT parent, created FROM sanket_maintain_partitions()"))).all()
        await conn.commit()
    created = {r[0]: r[1] for r in rows}
    assert "trend_signals" in created
    assert created["trend_signals"] == 0  # the migration already provisioned the window
