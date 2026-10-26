"""Split a completed SKU forecast run across locations (location spec §4).

The SKU forecast stays authoritative; this writes share_split_v1 rows to
location_forecast_results and records coverage of the split on the run.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal as D

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import current_week_start, week_bucket, week_start_instant
from app.models.enums import IndustryCode
from app.models.forecast import ForecastResult, ForecastRun
from app.models.location import LocationForecastResult
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.services.decision_engine import DemandBand
from app.services.location_shares import (
    WINDOW_WEEKS, ShareResult, WeekObs, blend_shares, shares_from_obs, split_week,
)
from app.services.locations import load_locations, sync_locations

METHOD = "share_split_v1"
DEGRADED_UNASSIGNED_SHARE = 0.05


@dataclass
class SplitSummary:
    series: int
    excluded: list[dict[str, str]] = field(default_factory=list)
    unassigned_share: float = 0.0
    degraded: bool = False


async def split_run_by_location(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, run_id: uuid.UUID, now: datetime
) -> SplitSummary:
    ind = IndustryCode(industry)
    this_week = current_week_start(now)
    weeks = [this_week - timedelta(weeks=WINDOW_WEEKS - i) for i in range(WINDOW_WEEKS)]

    await sync_locations(session, tenant_id)
    loc_ids = {l.code: l.id for l in await load_locations(session, tenant_id) if l.is_active}

    fc = (await session.execute(
        select(ForecastResult.sku_id, ForecastResult.forecast_date,
               func.avg(ForecastResult.p10), func.avg(ForecastResult.p50),
               func.avg(ForecastResult.p90))
        .where(ForecastResult.tenant_id == tenant_id, ForecastResult.run_id == run_id)
        .group_by(ForecastResult.sku_id, ForecastResult.forecast_date)
    )).all()
    weekly: dict[uuid.UUID, list[tuple[date, float, float, float]]] = defaultdict(list)
    for sku_id, d, p10, p50, p90 in fc:
        weekly[sku_id].append((d, float(p10), float(p50), float(p90)))

    category = dict((await session.execute(
        select(Sku.id, Product.category).join(Product, Product.id == Sku.product_id)
        .where(Sku.tenant_id == tenant_id, Sku.id.in_(list(weekly)))
    )).all())

    bucket = week_bucket(HistoricalSale.sale_time).label("week")
    loc_key = func.lower(func.btrim(HistoricalSale.location)).label("loc")
    sales = (await session.execute(
        select(HistoricalSale.sku_id, bucket, loc_key,
               func.sum(HistoricalSale.units_sold).label("units"),
               func.bool_or(HistoricalSale.in_stock.is_(False)).label("oos"))
        .where(HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == ind,
               HistoricalSale.sale_time >= week_start_instant(weeks[0]),
               HistoricalSale.sale_time < week_start_instant(this_week))
        .group_by(HistoricalSale.sku_id, bucket, loc_key)
    )).all()

    sku_obs: dict[uuid.UUID, list[WeekObs]] = defaultdict(list)
    cat_obs: dict[str, list[WeekObs]] = defaultdict(list)
    total_units = unassigned_units = 0.0
    for r in sales:
        code = r.loc if r.loc and r.loc not in ("", "default") else None
        units = float(r.units or 0)
        wk = r.week.date() if isinstance(r.week, datetime) else r.week
        total_units += units
        if code is None:
            unassigned_units += units
        sku_obs[r.sku_id].append(WeekObs(wk, code, units, False if r.oos else None))
        cat = category.get(r.sku_id)
        if cat is not None:
            cat_obs[cat].append(WeekObs(wk, code, units, None))

    cat_shares: dict[str, ShareResult] = {c: shares_from_obs(o, weeks) for c, o in cat_obs.items()}

    await session.execute(delete(LocationForecastResult).where(
        LocationForecastResult.tenant_id == tenant_id, LocationForecastResult.run_id == run_id))

    rows: list[dict] = []
    series = 0
    excluded: list[dict[str, str]] = []
    for sku_id, band in weekly.items():
        own = shares_from_obs(sku_obs.get(sku_id, []), weeks)
        blended = blend_shares(own, cat_shares.get(category.get(sku_id)))
        if not blended.shares:
            excluded.append({"sku_id": str(sku_id),
                             "reason": "No sales history for this SKU or its category"})
            continue
        for code, share in blended.shares.items():
            loc_id = loc_ids.get(code)
            if loc_id is None:
                continue
            series += 1
            for d, p10, p50, p90 in band:
                lp10, lp50, lp90 = split_week(p10, p50, p90, share)
                rows.append({
                    "id": uuid.uuid4(), "tenant_id": tenant_id, "run_id": run_id,
                    "sku_id": sku_id, "location_id": loc_id, "forecast_date": d,
                    "p10": D(str(round(lp10, 4))), "p50": D(str(round(lp50, 4))),
                    "p90": D(str(round(lp90, 4))), "share": D(str(round(share, 6))),
                    "share_basis": blended.basis[code], "method": METHOD,
                })
    for start in range(0, len(rows), 5000):
        await session.execute(insert(LocationForecastResult), rows[start : start + 5000])

    unassigned_share = unassigned_units / total_units if total_units > 0 else 0.0
    summary = SplitSummary(series=series, excluded=excluded,
                           unassigned_share=round(unassigned_share, 6),
                           degraded=unassigned_share > DEGRADED_UNASSIGNED_SHARE)
    await session.execute(
        text("UPDATE forecast_runs SET metrics = metrics || CAST(:m AS jsonb) WHERE id = :r"),
        {"r": str(run_id), "m": json.dumps({
            "location_series": summary.series, "location_excluded": len(excluded),
            "unassigned_share": summary.unassigned_share,
            "location_degraded": summary.degraded})},
    )
    return summary


async def ensure_location_split(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, run: ForecastRun, now: datetime
) -> SplitSummary | None:
    exists = await session.scalar(
        select(LocationForecastResult.id).where(
            LocationForecastResult.tenant_id == tenant_id,
            LocationForecastResult.run_id == run.id).limit(1))
    if exists is not None:
        return None
    return await split_run_by_location(session, tenant_id=tenant_id, industry=industry,
                                       run_id=run.id, now=now)


async def location_bands(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID, now: datetime
) -> dict[tuple[uuid.UUID, uuid.UUID], DemandBand]:
    rows = (await session.execute(
        select(LocationForecastResult.sku_id, LocationForecastResult.location_id,
               LocationForecastResult.p10, LocationForecastResult.p50, LocationForecastResult.p90)
        .where(LocationForecastResult.tenant_id == tenant_id,
               LocationForecastResult.run_id == run_id,
               LocationForecastResult.forecast_date >= current_week_start(now))
        .order_by(LocationForecastResult.sku_id, LocationForecastResult.location_id,
                  LocationForecastResult.forecast_date)
    )).all()
    acc: dict[tuple[uuid.UUID, uuid.UUID], tuple[list, list, list]] = {}
    for sku_id, loc_id, p10, p50, p90 in rows:
        b = acc.setdefault((sku_id, loc_id), ([], [], []))
        b[0].append(float(p10)); b[1].append(float(p50)); b[2].append(float(p90))
    return {k: DemandBand(p10=v[0], p50=v[1], p90=v[2]) for k, v in acc.items()}
