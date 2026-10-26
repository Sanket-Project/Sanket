"""The dated input-readiness contract every planning service shares.

Coverage, decisions and the scenario simulator all turn the same three inputs —
a forecast run, recorded stock and supplier lead time — into planning output.
They used to judge those inputs differently: coverage refused a forecast older
than two weeks or stock older than a month, while decisions and the simulator
took the latest run of any age, read weeks already in the past as if they were
upcoming demand, and treated a SKU with no stock record as holding zero.

The thresholds and checks live here so the three cannot drift apart again.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import current_week_start
from app.models.forecast import ForecastResult
from app.services.decision_engine import DemandBand

#: A forecast completed more than this many days ago is not a basis for action.
FORECAST_MAX_AGE_DAYS = 14
#: A stock position recorded more than this many days ago is not current.
STALE_STOCK_DAYS = 30


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def run_age_days(run: Any, now: datetime) -> float | None:
    """Days since the run completed, or None when it has no completion time."""
    if run is None or run.completed_at is None:
        return None
    return round((now - _utc(run.completed_at)).total_seconds() / 86400, 1)


def is_run_fresh(run: Any, now: datetime) -> bool:
    age = run_age_days(run, now)
    return age is not None and age <= FORECAST_MAX_AGE_DAYS


def stock_is_stale(as_of: datetime | None, now: datetime) -> bool:
    return as_of is None or now - _utc(as_of) > timedelta(days=STALE_STOCK_DAYS)


async def future_forecast_bands(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID, now: datetime
) -> dict[uuid.UUID, DemandBand]:
    """Weekly p10/p50/p90 per SKU from the current UTC week forward.

    Weeks before the current one are history the run happened to cover, not
    demand still to come. Rows for the same (sku, week) from several models are
    averaged, as in :func:`decision_builder.forecast_bands`.
    """
    rows = (
        await session.execute(
            select(
                ForecastResult.sku_id,
                ForecastResult.forecast_date,
                func.avg(ForecastResult.p10).label("p10"),
                func.avg(ForecastResult.p50).label("p50"),
                func.avg(ForecastResult.p90).label("p90"),
            )
            .where(
                ForecastResult.run_id == run_id,
                ForecastResult.tenant_id == tenant_id,
                ForecastResult.forecast_date >= current_week_start(now),
            )
            .group_by(ForecastResult.sku_id, ForecastResult.forecast_date)
            .order_by(ForecastResult.sku_id, ForecastResult.forecast_date)
        )
    ).fetchall()

    buckets: dict[uuid.UUID, tuple[list[float], list[float], list[float]]] = {}
    for r in rows:
        p10s, p50s, p90s = buckets.setdefault(r.sku_id, ([], [], []))
        p10s.append(float(r.p10 or 0))
        p50s.append(float(r.p50 or 0))
        p90s.append(float(r.p90 or 0))
    return {
        sku_id: DemandBand(p10=p10s, p50=p50s, p90=p90s)
        for sku_id, (p10s, p50s, p90s) in buckets.items()
    }
