"""Constant-rate planning estimates from reported period totals, never invented history."""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Product, Sku
from app.services.planning_inputs import stock_is_stale

MAX_PERIOD_AGE_DAYS = 90


def period_rate(attributes: dict | None, now: datetime, location: str | None = None) -> dict | None:
    """A positive observed average; absent, nonpositive and stale totals are not zero demand."""
    data = (attributes or {}).get("period_sales")
    if not isinstance(data, dict):
        return None
    try:
        start, end = date.fromisoformat(data["start"]), date.fromisoformat(data["end"])
        days = (end - start).days + 1
        age = (now.date() - end).days
        units = data.get("units") if location is None else (data.get("locations") or {}).get(location.strip().lower())
        if isinstance(units, bool):
            return None
        units = float(units)
        if days < 1 or age < 0 or age > MAX_PERIOD_AGE_DAYS or not math.isfinite(units) or units <= 0 or not data.get("source"):
            return None
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return {"daily_units": units / days, "weekly_units": units * 7 / days,
            "reported_units": units, "days": days, "start": start.isoformat(),
            "end": end.isoformat(), "source": data["source"], "age_days": age}


def rate_reason(rate: dict) -> str:
    return (f"Average-sales estimate: {rate['reported_units']:g} reported units / {rate['days']} days "
            f"({rate['start']} to {rate['end']}); assumes the same daily rate. "
            "Seasonality, recent trends and stockouts are not measured.")


async def projection(db, tenant_id: uuid.UUID, industry: str, *, horizon_weeks: int = 12,
                     offset: int = 0, limit: int = 25, search: str = "", now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    ind = IndustryCode(industry)
    async with db.session(str(tenant_id)) as session:
        scope = [Sku.tenant_id == tenant_id, Sku.industry == ind, Sku.is_active.is_(True)]
        total = await session.scalar(select(func.count()).select_from(Sku).where(*scope))
        candidates = (await session.execute(select(Sku, Product.name).join(Product, Product.id == Sku.product_id)
            .where(*scope, Product.tenant_id == tenant_id, Sku.attributes["period_sales"].astext.is_not(None))
            .order_by(Sku.sku_code, Sku.id))).all()
        eligible = [(sku, name, rate) for sku, name in candidates if (rate := period_rate(sku.attributes, now))]
        term = search.strip().casefold()
        filtered = [(sku, name, rate) for sku, name, rate in eligible if not term or term in sku.sku_code.casefold() or term in name.casefold()]
        page = filtered[offset:offset + limit]
        ids = [sku.id for sku, _, _ in page]
        stock = (await session.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tenant_id,
            InventoryLevel.industry == ind, InventoryLevel.sku_id.in_(ids)))).scalars().all() if ids else []
    by_sku = defaultdict(list)
    for level in stock:
        by_sku[level.sku_id].append(level)
    rows = []
    for sku, name, rate in page:
        levels = by_sku[sku.id]
        fresh = bool(levels) and not any(stock_is_stale(level.as_of, now) for level in levels)
        available = sum(float(level.available_units) for level in levels)
        locations = []
        for level in sorted(levels, key=lambda r: r.location):
            local = period_rate(sku.attributes, now, level.location)
            local_fresh = not stock_is_stale(level.as_of, now)
            locations.append({"location": level.location, "available_units": float(level.available_units),
                "weekly_units": local["weekly_units"] if local else None,
                "projected_units": local["daily_units"] * horizon_weeks * 7 if local else None,
                "estimated_cover_days": round(float(level.available_units) / local["daily_units"], 1) if local and local_fresh else None,
                "reason": rate_reason(local) if local else "No positive matching SKU/location period sales; local projection unavailable."})
        rows.append({"sku_id": str(sku.id), "sku_code": sku.sku_code, "product_name": name,
            **rate, "projected_units": rate["daily_units"] * horizon_weeks * 7,
            "available_units": available, "estimated_cover_days": round(available / rate["daily_units"], 1) if fresh else None,
            "locations": locations})
    periods = sorted({(rate["start"], rate["end"], rate["days"], rate["source"]) for _, _, rate in eligible})
    return {"status": "available" if eligible else "unavailable", "basis": "period_average",
        "industry": industry, "as_of": now.isoformat(), "horizon_weeks": horizon_weeks,
        "projection_start": now.date().isoformat(), "projection_end": (now.date() + timedelta(days=horizon_weeks * 7 - 1)).isoformat(),
        "catalogue_skus": total, "matched_skus": len(candidates), "eligible_skus": len(eligible),
        "missing_skus": total - len(candidates), "unsupported_skus": len(candidates) - len(eligible),
        "filtered_skus": len(filtered), "offset": offset, "limit": limit,
        "projected_units": sum(rate["daily_units"] * horizon_weeks * 7 for _, _, rate in filtered),
        "source_periods": [{"start": start, "end": end, "days": days, "source": source} for start, end, days, source in periods],
        "uncertainty": None, "model_run_id": None, "rows": rows,
        "limitations": ["Constant average-sales projection; not a Chronos model forecast. No confidence interval is available.",
            "Missing and nonpositive sales totals are excluded, not treated as zero demand. Source periods over 90 days old are unavailable.",
            "Assumes the same daily selling rate across the full source period and future horizon; seasonality, recent trends, launch dates and stockouts are not measured.",
            "Stock cover is an estimate. Confirm the stock snapshot date and supplier lead times before ordering. No purchase or transfer decisions are generated from this projection."]}
