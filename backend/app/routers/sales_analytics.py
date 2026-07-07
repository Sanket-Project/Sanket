"""Sales analytics router — live + historical sales for the active tenant.

Aggregates `historical_sales` into the KPI windows a company cares about
(today / week / month / year) plus a bucketed time series and a top-products
breakdown. A small ingest endpoint records a sale and fans it out over the
realtime WebSocket so dashboards tick up live.

Everything is tenant-scoped (a tenant = one registered company) and respects
the active industry, exactly like the financial/anomaly routers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy import text as sa_text

from app.config import get_settings
from app.core.cache import get_response_cache
from app.models.enums import IndustryCode
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.routers.industry_router import ActiveIndustry, TenantId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/analytics/sales", tags=["sales-analytics"])


# ── helpers ──────────────────────────────────────────────────────────────────


def _day_start(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _period_bounds(now: datetime, period: str) -> tuple[datetime, datetime]:
    """Return (current_start, previous_start) for a named period.

    The previous window is the same calendar period one step back; callers
    compare equal *elapsed* slices of each so a mid-period total isn't unfairly
    measured against a full prior period.
    """
    today = _day_start(now)
    if period == "today":
        start = today
        prev = start - timedelta(days=1)
    elif period == "week":
        start = today - timedelta(days=today.weekday())  # Monday 00:00
        prev = start - timedelta(weeks=1)
    elif period == "month":
        start = today.replace(day=1)
        prev = (start - timedelta(days=1)).replace(day=1)
    elif period == "year":
        start = today.replace(month=1, day=1)
        prev = start.replace(year=start.year - 1)
    else:
        raise ValueError(f"unknown period {period!r}")
    return start, prev


def _delta(current: float, previous: float) -> float | None:
    """Fractional change vs the prior window, or None when there's no baseline."""
    if previous <= 0:
        return None
    return round((current - previous) / previous, 4)


# ── summary KPIs ─────────────────────────────────────────────────────────────


@router.get("/summary")
async def sales_summary(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> dict[str, Any]:
    """KPI cards for today / this week / this month / this year.

    Each bucket reports units, gross & net revenue, returns and transaction
    count, plus a revenue delta vs the equal elapsed slice of the prior period.

    Computation: one aggregate query per (period, window). These are kept as
    *narrow-window* scans on purpose — benchmarking showed that collapsing them
    into a single ``SUM(...) FILTER (...)`` query is ~1.5x SLOWER, because the
    single query must scan the whole ``[year_prior_start, now)`` union and apply
    every filter per row, whereas the windowed queries each touch only their own
    (mostly tiny: today / week / month) slice. The real latency win here is the
    response cache wrapping this producer — repeated dashboard polls are served
    from Redis in well under a millisecond instead of re-aggregating. See
    docs/PERFORMANCE.md and benchmarks/bench_sales_summary.py.
    """
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    now = datetime.now(UTC)
    periods: list[str] = ["today", "week", "month", "year"]

    async def _aggregate(session, start: datetime, end: datetime) -> dict[str, float | int]:
        row = (
            await session.execute(
                select(
                    func.coalesce(func.sum(HistoricalSale.units_sold), 0).label("units"),
                    func.coalesce(func.sum(HistoricalSale.gross_revenue), 0).label("gross"),
                    func.coalesce(func.sum(HistoricalSale.net_revenue), 0).label("net"),
                    func.coalesce(func.sum(HistoricalSale.returns), 0).label("returns"),
                    func.count().label("transactions"),
                ).where(
                    HistoricalSale.tenant_id == tenant_id,
                    HistoricalSale.industry == industry,
                    HistoricalSale.sale_time >= start,
                    HistoricalSale.sale_time < end,
                )
            )
        ).one()
        return {
            "units_sold": int(row.units or 0),
            "gross_revenue": float(row.gross or 0),
            "net_revenue": float(row.net or 0),
            "returns": int(row.returns or 0),
            "transactions": int(row.transactions or 0),
        }

    async def _compute() -> dict[str, Any]:
        result: dict[str, Any] = {"industry": ctx.code, "as_of": now.isoformat()}
        async with db.session(str(tenant_id)) as session:
            for period in periods:
                start, prev_start = _period_bounds(now, period)
                elapsed = now - start
                current = await _aggregate(session, start, now)
                previous = await _aggregate(session, prev_start, prev_start + elapsed)
                result[period] = {
                    **current,
                    "period_start": start.isoformat(),
                    "revenue_delta": _delta(current["gross_revenue"], previous["gross_revenue"]),
                    "units_delta": _delta(current["units_sold"], previous["units_sold"]),
                }
        return result

    cache = get_response_cache(request)
    return await cache.get_or_set(
        tenant_id=tenant_id,
        name="sales:summary",
        params={"industry": ctx.code},
        ttl_s=get_settings().api_cache_ttl_s,
        producer=_compute,
    )


# ── time series ──────────────────────────────────────────────────────────────


def _step(d: datetime, granularity: str) -> datetime:
    if granularity == "day":
        return d + timedelta(days=1)
    if granularity == "week":
        return d + timedelta(weeks=1)
    # month
    year, month = d.year + (d.month // 12), (d.month % 12) + 1
    return d.replace(year=year, month=month, day=1)


def _trunc_start(d: datetime, granularity: str) -> datetime:
    base = _day_start(d)
    if granularity == "week":
        return base - timedelta(days=base.weekday())
    if granularity == "month":
        return base.replace(day=1)
    return base


@router.get("/timeseries")
async def sales_timeseries(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    granularity: Literal["day", "week", "month"] = "day",
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Bucketed units + revenue for charting. Gaps are zero-filled so the line
    is continuous even on days with no sales."""
    lookback_days = max(1, min(lookback_days, 730))
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    now = datetime.now(UTC)
    window_start = _trunc_start(now - timedelta(days=lookback_days), granularity)

    bucket = func.date_trunc(sa_text(f"'{granularity}'"), HistoricalSale.sale_time)

    async def _compute() -> dict[str, Any]:
        async with db.session(str(tenant_id)) as session:
            rows = (
                await session.execute(
                    select(
                        bucket.label("bucket"),
                        func.coalesce(func.sum(HistoricalSale.units_sold), 0).label("units"),
                        func.coalesce(func.sum(HistoricalSale.gross_revenue), 0).label("gross"),
                        func.coalesce(func.sum(HistoricalSale.net_revenue), 0).label("net"),
                    )
                    .where(
                        HistoricalSale.tenant_id == tenant_id,
                        HistoricalSale.industry == industry,
                        HistoricalSale.sale_time >= window_start,
                    )
                    .group_by(bucket)
                    .order_by(bucket)
                )
            ).fetchall()

        by_bucket = {
            _day_start(r.bucket.replace(tzinfo=UTC) if r.bucket.tzinfo is None else r.bucket): r
            for r in rows
        }

        series: list[dict] = []
        cursor = window_start
        while cursor <= now:
            key = _day_start(cursor)
            r = by_bucket.get(key)
            series.append(
                {
                    "bucket": cursor.date().isoformat(),
                    "units_sold": int(r.units) if r else 0,
                    "gross_revenue": float(r.gross) if r else 0.0,
                    "net_revenue": float(r.net) if r else 0.0,
                }
            )
            cursor = _step(cursor, granularity)

        return {
            "industry": ctx.code,
            "granularity": granularity,
            "lookback_days": lookback_days,
            "series": series,
        }

    cache = get_response_cache(request)
    return await cache.get_or_set(
        tenant_id=tenant_id,
        name="sales:timeseries",
        params={"industry": ctx.code, "granularity": granularity, "lookback_days": lookback_days},
        ttl_s=get_settings().api_cache_ttl_s,
        producer=_compute,
    )


# ── top products ─────────────────────────────────────────────────────────────


@router.get("/top-products")
async def top_products(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    period: Literal["today", "week", "month", "year", "all"] = "month",
    limit: int = 10,
) -> dict[str, Any]:
    """Best-selling SKUs (with product name) over the selected window."""
    limit = max(1, min(limit, 100))
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    now = datetime.now(UTC)

    filters = [
        HistoricalSale.tenant_id == tenant_id,
        HistoricalSale.industry == industry,
    ]
    if period != "all":
        start, _ = _period_bounds(now, period)
        filters.append(HistoricalSale.sale_time >= start)

    async def _compute() -> dict[str, Any]:
        async with db.session(str(tenant_id)) as session:
            rows = (
                await session.execute(
                    select(
                        HistoricalSale.sku_id,
                        func.sum(HistoricalSale.units_sold).label("units"),
                        func.coalesce(func.sum(HistoricalSale.gross_revenue), 0).label("gross"),
                        func.sum(HistoricalSale.returns).label("returns"),
                    )
                    .where(*filters)
                    .group_by(HistoricalSale.sku_id)
                    .order_by(func.sum(HistoricalSale.units_sold).desc())
                    .limit(limit)
                )
            ).fetchall()

            sku_ids = [r.sku_id for r in rows]
            names: dict[uuid.UUID, tuple[str, str]] = {}
            if sku_ids:
                meta = (
                    await session.execute(
                        select(Sku.id, Sku.sku_code, Product.name)
                        .join(Product, Product.id == Sku.product_id)
                        .where(Sku.tenant_id == tenant_id, Sku.id.in_(sku_ids))
                    )
                ).fetchall()
                names = {m.id: (m.sku_code, m.name) for m in meta}

        products = [
            {
                "sku_id": str(r.sku_id),
                "sku_code": names.get(r.sku_id, ("—", "Unknown SKU"))[0],
                "product_name": names.get(r.sku_id, ("—", "Unknown SKU"))[1],
                "units_sold": int(r.units or 0),
                "gross_revenue": float(r.gross or 0),
                "returns": int(r.returns or 0),
            }
            for r in rows
        ]
        return {"industry": ctx.code, "period": period, "products": products}

    cache = get_response_cache(request)
    return await cache.get_or_set(
        tenant_id=tenant_id,
        name="sales:top-products",
        params={"industry": ctx.code, "period": period, "limit": limit},
        ttl_s=get_settings().api_cache_ttl_s,
        producer=_compute,
    )


# ── live ingest ──────────────────────────────────────────────────────────────


class SaleIngest(BaseModel):
    sku_id: uuid.UUID
    units_sold: int = Field(ge=0)
    gross_revenue: Decimal | None = None
    net_revenue: Decimal | None = None
    returns: int = Field(default=0, ge=0)
    channel: str = "unknown"
    region: str | None = None
    sale_time: datetime | None = None


@router.post("/ingest", status_code=201)
async def ingest_sale(
    body: SaleIngest,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
) -> dict[str, Any]:
    """Record a single sale and broadcast it live to the tenant's dashboards.

    This is the hook a POS / Shopify / ERP feed calls. The realtime event lets
    the Analytics page increment its live counters without a refetch.
    """
    from app.realtime.events import EVENT_SALE_CREATED, RealtimeEvent

    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    sale_time = body.sale_time or datetime.now(UTC)
    if sale_time.tzinfo is None:
        sale_time = sale_time.replace(tzinfo=UTC)

    sale = HistoricalSale(
        tenant_id=tenant_id,
        sku_id=body.sku_id,
        industry=industry,
        sale_time=sale_time,
        channel=body.channel,
        region=body.region,
        units_sold=body.units_sold,
        gross_revenue=body.gross_revenue,
        net_revenue=body.net_revenue,
        returns=body.returns,
    )

    async with db.session(str(tenant_id)) as session:
        session.add(sale)
        await session.flush()
        sale_id = sale.id

    # Drop this tenant's cached analytics so the new sale is reflected on the
    # next read instead of waiting out the TTL (O(1) version bump).
    await get_response_cache(request).invalidate_tenant(tenant_id)

    # Fan out over WebSocket (best-effort — never fail the write on this).
    manager = getattr(request.app.state, "realtime", None)
    if manager is not None:
        try:
            await manager.publish(
                RealtimeEvent(
                    type=EVENT_SALE_CREATED,
                    tenant_id=tenant_id,
                    industry=ctx.code,
                    data={
                        "sale_id": str(sale_id),
                        "sku_id": str(body.sku_id),
                        "units_sold": body.units_sold,
                        "gross_revenue": float(body.gross_revenue or 0),
                        "net_revenue": float(body.net_revenue or 0),
                        "channel": body.channel,
                        "sale_time": sale_time.isoformat(),
                    },
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("sales.ingest.broadcast_failed", error=str(exc))

    log.info("sales.ingest", sku_id=str(body.sku_id), units=body.units_sold)
    return {"sale_id": str(sale_id), "sale_time": sale_time.isoformat()}
