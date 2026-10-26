"""Stock cover per SKU and per location, from demand, lead time and freshness.

The Inventory page used to call any position with 20+ units "healthy" unless a
purchase recommendation happened to exist, and showed the SKU's pooled cover on
every store row. Cover here is computed directly and independently of
recommendations:

* **Demand basis** — the latest forecast (not a backtest) completed within
  ``FORECAST_MAX_AGE_DAYS`` that includes the SKU (mean P50 of its next
  ``FORECAST_WEEKS`` weeks); otherwise the trailing ``TRAILING_WEEKS`` complete
  weeks of actual sales if at least ``MIN_WEEKS`` of them have sales; otherwise
  none, and cover is unknown — never assumed safe.
* **SKU-wide cover** pools available stock across every location.
* **Location cover** needs sales recorded at that location (``location`` on the
  sale). Without them it is ``None``, with the reason, rather than the pooled
  figure presented as a store's.

Status: unknown (no basis / no fresh stock), critical (cover <= lead time), low
(<= ``LOW_MULTIPLIER`` x lead time), excess (cover > ``EXCESS_MULTIPLIER`` x the
lead-time + review-period protection window — an approximation, in days of
cover on available stock, of the decision engine's excess-stock rule, which
also counts inbound units and safety stock), healthy. No transfer suggestions are made.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import CALENDAR, current_week_start, week_bucket, week_start_instant
from app.models.enums import IndustryCode
from app.models.forecast import ForecastResult
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.models.tenant import Tenant
from app.models.sales import HistoricalSale
from app.services.decision_builder import latest_completed_run, load_policy
from app.services.decision_engine import DEFAULT_LEAD_TIME_DAYS
from app.services.planning_inputs import (
    FORECAST_MAX_AGE_DAYS,
    STALE_STOCK_DAYS,
    is_run_fresh,
    stock_is_stale,
)

FORECAST_WEEKS = 4
TRAILING_WEEKS = 8
MIN_WEEKS = 4
LOW_MULTIPLIER = 1.5
#: Mirrors the multiplier of the decision engine's excess-stock decision
#: (position > 2 x order-up-to). Coverage applies it to days of cover on
#: available stock only, so it is an approximation of that rule, not a copy.
EXCESS_MULTIPLIER = 2
EXCESS_ACTION = (
    "Pause reorders, review inbound stock, and consider a transfer or markdown."
)

_POOLED = "Cover is SKU-wide (all locations pooled)"


def _status(cover_days: float | None, lead: int, review_days: int) -> str:
    if cover_days is None:
        return "healthy"  # demand basis exists and expects no sales
    if cover_days <= lead:
        return "critical"
    if cover_days <= lead * LOW_MULTIPLIER:
        return "low"
    if cover_days > EXCESS_MULTIPLIER * (lead + review_days):
        return "excess"
    return "healthy"


def _next_action(status: str | None) -> str | None:
    return EXCESS_ACTION if status == "excess" else None


def _cover(available: float, weekly: float) -> float | None:
    return round(available / (weekly / 7.0), 1) if weekly > 0 else None


def _trailing_mean(weeks: dict[date, float], last_week: date) -> tuple[float | None, int]:
    """Mean weekly units from the first sold week in the window to ``last_week``."""
    observed = len(weeks)
    if observed < MIN_WEEKS:
        return None, observed
    span = (last_week - min(weeks)).days // 7 + 1
    return round(sum(weeks.values()) / span, 2), observed


async def coverage(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    ind = IndustryCode(industry)
    this_week = current_week_start(now)
    window_start = this_week - timedelta(weeks=TRAILING_WEEKS)
    last_week = this_week - timedelta(weeks=1)
    tenant = await session.get(Tenant, tenant_id)
    review_days = load_policy(tenant.settings if tenant else None).review_period_days

    stock_rows = (
        await session.execute(
            select(InventoryLevel, Sku.sku_code, Sku.lead_time_days)
            .join(Sku, Sku.id == InventoryLevel.sku_id)
            .where(InventoryLevel.tenant_id == tenant_id, InventoryLevel.industry == ind)
        )
    ).all()
    if not stock_rows:
        return _envelope(now, [], review_days)
    sku_ids = list({lvl.sku_id for lvl, _, _ in stock_rows})

    # Forecast basis: the latest real (non-backtest) run, if recent enough.
    forecast_weekly: dict[uuid.UUID, float] = {}
    run = await latest_completed_run(session, tenant_id, ind)
    if is_run_fresh(run, now):
        rows = (
            await session.execute(
                select(ForecastResult.sku_id, ForecastResult.forecast_date,
                       func.avg(ForecastResult.p50).label("p50"))
                .where(
                    ForecastResult.tenant_id == tenant_id,
                    ForecastResult.run_id == run.id,
                    ForecastResult.sku_id.in_(sku_ids),
                    ForecastResult.forecast_date >= this_week,
                )
                .group_by(ForecastResult.sku_id, ForecastResult.forecast_date)
                .order_by(ForecastResult.sku_id, ForecastResult.forecast_date)
            )
        ).all()
        per_sku: dict[uuid.UUID, list[float]] = defaultdict(list)
        for r in rows:
            if len(per_sku[r.sku_id]) < FORECAST_WEEKS:
                per_sku[r.sku_id].append(float(r.p50 or 0))
        forecast_weekly = {k: round(sum(v) / len(v), 2) for k, v in per_sku.items() if v}

    # Trailing complete weeks of actuals, per SKU and per (SKU, location).
    bucket = week_bucket(HistoricalSale.sale_time).label("week")
    loc_key = func.lower(func.trim(HistoricalSale.location)).label("loc")
    sales = (
        await session.execute(
            select(HistoricalSale.sku_id, bucket, loc_key,
                   func.sum(HistoricalSale.units_sold).label("units"))
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == ind,
                HistoricalSale.sku_id.in_(sku_ids),
                HistoricalSale.sale_time >= week_start_instant(window_start),
                HistoricalSale.sale_time < week_start_instant(this_week),
            )
            .group_by(HistoricalSale.sku_id, bucket, loc_key)
        )
    ).all()
    sku_weeks: dict[uuid.UUID, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    loc_weeks: dict[tuple[uuid.UUID, str], dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for r in sales:
        wk = r.week.date()
        sku_weeks[r.sku_id][wk] += float(r.units or 0)
        if r.loc:
            loc_weeks[(r.sku_id, r.loc)][wk] += float(r.units or 0)

    by_sku: dict[uuid.UUID, list] = defaultdict(list)
    meta: dict[uuid.UUID, tuple[str, int | None]] = {}
    for lvl, code, lead in stock_rows:
        by_sku[lvl.sku_id].append(lvl)
        meta[lvl.sku_id] = (code, lead)

    out = []
    for sku_id, levels in by_sku.items():
        code, lead_raw = meta[sku_id]
        lead = int(lead_raw) if lead_raw is not None else DEFAULT_LEAD_TIME_DAYS

        if sku_id in forecast_weekly:
            weekly, basis = forecast_weekly[sku_id], "forecast"
            demand_reason = f"Mean P50 of the next {FORECAST_WEEKS} forecast weeks."
        else:
            weekly, observed = _trailing_mean(sku_weeks.get(sku_id, {}), last_week)
            basis = "trailing_actuals" if weekly is not None else None
            demand_reason = (
                f"Mean weekly sales over the last complete weeks ({observed} of "
                f"{TRAILING_WEEKS} with sales)."
                if basis
                else f"No demand basis: no forecast from the last {FORECAST_MAX_AGE_DAYS} days and "
                f"only {observed} of the last {TRAILING_WEEKS} weeks have sales."
            )

        stale = [lvl for lvl in levels if stock_is_stale(lvl.as_of, now)]
        available = sum(float(lvl.available_units) for lvl in levels)
        inbound = sum(float(lvl.inbound_units or 0) for lvl in levels)

        if not basis:
            sku_status, sku_cover, sku_reason = "unknown", None, demand_reason
        elif stale:
            age = max((now - lvl.as_of).days for lvl in stale if lvl.as_of) if any(
                lvl.as_of for lvl in stale) else None
            sku_status, sku_cover = "unknown", None
            sku_reason = (
                f"Stock at {', '.join(lvl.location for lvl in stale)} was last updated "
                f"{age} days ago" if age is not None else "Stock has no as-of date"
            ) + f"; cover needs a stock position from the last {STALE_STOCK_DAYS} days."
        else:
            sku_cover = _cover(available, weekly or 0.0)
            sku_status = _status(sku_cover, lead, review_days)
            sku_reason = (
                "No sales expected over the window." if sku_cover is None
                else f"{_POOLED}: {available:g} available / {weekly:g} units a week."
            )

        locations = []
        for lvl in sorted(levels, key=lambda x: x.location):
            loc_weekly, loc_observed = _trailing_mean(
                loc_weeks.get((sku_id, lvl.location.strip().lower()), {}), last_week
            )
            loc_stale = lvl in stale
            if loc_weekly is None:
                loc_cover, loc_status = None, None
                loc_reason = (
                    f"{_POOLED} — fewer than {MIN_WEEKS} of the last {TRAILING_WEEKS} weeks "
                    f"have sales recorded at {lvl.location}."
                )
            elif loc_stale:
                loc_cover, loc_status = None, "unknown"
                loc_reason = "Stock position at this location is out of date."
            else:
                loc_cover = _cover(float(lvl.available_units), loc_weekly)
                loc_status = _status(loc_cover, lead, review_days)
                loc_reason = (
                    f"Location sales: {loc_weekly:g} units a week over {loc_observed} week(s)."
                )
            locations.append(
                {
                    "location": lvl.location,
                    "available_units": float(lvl.available_units),
                    "on_hand_units": float(lvl.on_hand_units or 0),
                    "inbound_units": float(lvl.inbound_units or 0),
                    "as_of": lvl.as_of.isoformat() if lvl.as_of else None,
                    "stock_stale": loc_stale,
                    "location_demand": {
                        "weekly_units": loc_weekly,
                        "weeks_observed": loc_observed,
                        "basis": "location_sales" if loc_weekly is not None else None,
                    },
                    "cover_days": loc_cover,
                    "status": loc_status,
                    "next_action": _next_action(loc_status),
                    "reason": loc_reason,
                }
            )

        out.append(
            {
                "sku_id": str(sku_id),
                "sku_code": code,
                "lead_time_days": lead,
                "lead_time_assumed": lead_raw is None,
                "demand": {
                    "basis": basis,
                    "weekly_units": weekly,
                    "run_id": str(run.id) if basis == "forecast" and run else None,
                    "reason": demand_reason,
                },
                "sku_wide": {
                    "available_units": available,
                    "inbound_units": inbound,
                    "cover_days": sku_cover,
                    "status": sku_status,
                    "next_action": _next_action(sku_status),
                    "reason": sku_reason,
                },
                "locations": locations,
            }
        )
    out.sort(key=lambda s: s["sku_code"] or "")
    return _envelope(now, out, review_days)


def _envelope(now: datetime, skus: list[dict], review_days: int) -> dict[str, Any]:
    return {
        "as_of": now.isoformat(),
        "calendar": CALENDAR,
        "policy": {
            "forecast_max_age_days": FORECAST_MAX_AGE_DAYS,
            "forecast_weeks": FORECAST_WEEKS,
            "trailing_weeks": TRAILING_WEEKS,
            "min_weeks": MIN_WEEKS,
            "stale_stock_days": STALE_STOCK_DAYS,
            "low_multiplier": LOW_MULTIPLIER,
            "excess_multiplier": EXCESS_MULTIPLIER,
            "review_period_days": review_days,
            "transfer_suggestions": False,
        },
        "skus": skus,
    }

