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
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy import text as sa_text

from app.config import get_settings
from app.core.cache import get_response_cache
from app.core.exceptions import ConflictError
from app.core.rbac import require_admin_db
from app.models.enums import IndustryCode
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId, UserId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/analytics/sales", tags=["sales-analytics"])


@router.delete("/all")
async def clear_sales(request: Request, ctx: ActiveIndustry, tenant_id: TenantId,
                      user_id: UserId, _rbac: Annotated[None, require_admin_db]) -> dict[str, Any]:
    """Permanently clear the active industry's sales and related import identities."""
    async with request.app.state.db.session(str(tenant_id)) as session:
        params = {"tenant": tenant_id, "industry": ctx.code}
        # V2 events lack an industry field; a unique SKU match is required to scope them.
        ambiguous = await session.scalar(sa_text("""
            SELECT count(*) FROM v2_sales_events e WHERE e.tenant_id=:tenant
              AND (SELECT count(*) FROM skus s WHERE s.tenant_id=e.tenant_id
                   AND lower(s.sku_code)=lower(e.sku_code)) <> 1
        """), params)
        unlinked_returns = await session.scalar(sa_text("""SELECT count(*) FROM v2_return_events
            WHERE tenant_id=:tenant AND sale_event_id IS NULL"""), params)
        if ambiguous or unlinked_returns:
            raise ConflictError("Some imported sales cannot be matched uniquely to an industry; sales were not deleted.")
        ids = (await session.execute(sa_text("""
            SELECT e.id FROM v2_sales_events e JOIN skus s ON s.tenant_id=e.tenant_id
              AND lower(s.sku_code)=lower(e.sku_code)
            WHERE e.tenant_id=:tenant AND s.industry=CAST(:industry AS industry_code)
        """), params)).scalars().all()
        if ids:
            params["ids"] = ids
            await session.execute(sa_text("""DELETE FROM event_identity_registry WHERE tenant_id=:tenant AND entity_kind='return'
                AND target_id IN (SELECT id FROM v2_return_events WHERE tenant_id=:tenant AND sale_event_id=ANY(:ids))"""), params)
            await session.execute(sa_text("DELETE FROM v2_return_events WHERE tenant_id=:tenant AND sale_event_id=ANY(:ids)"), params)
            await session.execute(sa_text("DELETE FROM event_identity_registry WHERE tenant_id=:tenant AND entity_kind='sale' AND target_id=ANY(:ids)"), params)
            await session.execute(sa_text("DELETE FROM v2_sales_events WHERE tenant_id=:tenant AND id=ANY(:ids)"), params)
        deleted = await session.scalar(sa_text("SELECT sanket_clear_sales(CAST(:industry AS industry_code))"), params)
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
        settings = dict(tenant.settings or {})
        if isinstance(settings.get("client_reports"), dict) and settings["client_reports"].get("industry") == ctx.code:
            del settings["client_reports"]
            tenant.settings = settings
    await get_response_cache(request).invalidate_tenant(tenant_id)
    log.info("sales.all_deleted", tenant=str(tenant_id), industry=ctx.code, user=str(user_id), deleted=deleted)
    return {"deleted": deleted, "industry": ctx.code}


@router.get("/client-reports")
async def client_reports(request: Request, ctx: ActiveIndustry, tenant_id: TenantId) -> dict[str, Any]:
    """Return imported aggregate reports without treating them as SKU transactions."""
    async with request.app.state.db.session(str(tenant_id)) as session:
        settings = await session.scalar(select(Tenant.settings).where(Tenant.id == tenant_id))
    report = (settings or {}).get("client_reports")
    if not isinstance(report, dict) or report.get("industry") != ctx.code:
        return {"status": "unavailable", "report": None}
    return {"status": "available", "report": report}


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


#: Revenue is denominated in the SKU's currency (sales rows carry none of
#: their own). Orphaned sales with no SKU have no known currency.
_SKU_CURRENCY = func.coalesce(Sku.currency, "unknown").label("currency")

# V2 identifies return events explicitly. Legacy uploads represent standalone
# returns with zero sold units, returned units and a negative gross amount.
# Do not exclude aggregate sales rows merely because they also report returns.
_RETURN_EVENT = or_(
    func.coalesce(HistoricalSale.metadata_["event_kind"].astext, "sale") == "return",
    and_(HistoricalSale.units_sold == 0, HistoricalSale.returns > 0,
         HistoricalSale.gross_revenue < 0),
)
_GROSS_BEFORE_RETURNS = case((_RETURN_EVENT, 0), else_=HistoricalSale.gross_revenue)


def _money(rows: list[Any]) -> dict[str, Any]:
    """Revenue for one bucket, per currency; summed only when there is one.

    Adding rupees to dollars produces a number in no currency at all, so a
    bucket with several currencies reports ``gross_revenue``/``net_revenue`` as
    ``None`` and the per-currency figures in ``revenue_by_currency``.
    """
    gross = {r.currency: float(r.gross or 0) for r in rows if (r.gross or r.net)}
    net = {r.currency: float(r.net or 0) for r in rows if (r.gross or r.net)}
    single = len(gross) <= 1
    return {
        "currency": next(iter(gross)) if len(gross) == 1 else None,
        "gross_revenue": sum(gross.values()) if single else None,
        "net_revenue": sum(net.values()) if single else None,
        "revenue_by_currency": gross,
        "net_revenue_by_currency": net,
    }


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

    async def _aggregate(session, start: datetime, end: datetime) -> dict[str, Any]:
        rows = (
            await session.execute(
                select(
                    _SKU_CURRENCY,
                    func.coalesce(func.sum(HistoricalSale.units_sold), 0).label("units"),
                    func.coalesce(func.sum(_GROSS_BEFORE_RETURNS), 0).label("gross"),
                    func.coalesce(func.sum(HistoricalSale.net_revenue), 0).label("net"),
                    func.coalesce(func.sum(HistoricalSale.returns), 0).label("returns"),
                    func.count().filter(
                        ~func.coalesce(_RETURN_EVENT, False)
                    ).label("transactions"),
                )
                .select_from(HistoricalSale)
                .outerjoin(Sku, Sku.id == HistoricalSale.sku_id)
                .where(
                    HistoricalSale.tenant_id == tenant_id,
                    HistoricalSale.industry == industry,
                    HistoricalSale.sale_time >= start,
                    HistoricalSale.sale_time < end,
                )
                .group_by(_SKU_CURRENCY)
            )
        ).all()
        return {
            "units_sold": int(sum(r.units or 0 for r in rows)),
            **_money(rows),
            "returns": int(sum(r.returns or 0 for r in rows)),
            "transactions": int(sum(r.transactions or 0 for r in rows)),
        }

    async def _compute() -> dict[str, Any]:
        result: dict[str, Any] = {"industry": ctx.code, "as_of": now.isoformat()}
        seen: set[str] = set()
        async with db.session(str(tenant_id)) as session:
            for period in periods:
                start, prev_start = _period_bounds(now, period)
                elapsed = now - start
                current = await _aggregate(session, start, now)
                previous = await _aggregate(session, prev_start, prev_start + elapsed)
                seen.update(current["revenue_by_currency"])
                comparable = (
                    current["currency"] is not None
                    and current["currency"] == (previous["currency"] or current["currency"])
                )
                result[period] = {
                    **current,
                    "period_start": start.isoformat(),
                    # A change in rupees vs a mix of currencies is not a percentage.
                    "revenue_delta": (
                        _delta(current["gross_revenue"] or 0.0, previous["gross_revenue"] or 0.0)
                        if comparable
                        else None
                    ),
                    "units_delta": _delta(current["units_sold"], previous["units_sold"]),
                }
        result["currencies"] = sorted(seen)
        result["currency"] = result["currencies"][0] if len(seen) == 1 else None
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
    """Bucketed units + revenue for charting.

    Buckets from the tenant's first recorded sale onward are zero-filled: a
    bucket with no sales after trading began is an observed zero. Buckets before
    the first sale are ``None`` — there are no records, which is not the same as
    selling nothing. ``units_sold`` is gross units; returns are not netted.
    """
    lookback_days = max(1, min(lookback_days, 730))
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    now = datetime.now(UTC)
    window_start = _trunc_start(now - timedelta(days=lookback_days), granularity)

    # Buckets in UTC explicitly, matching the weekly calendar (app.core.calendar).
    bucket = func.date_trunc(
        sa_text(f"'{granularity}'"), func.timezone("UTC", HistoricalSale.sale_time)
    )

    async def _compute() -> dict[str, Any]:
        async with db.session(str(tenant_id)) as session:
            rows = (
                await session.execute(
                    select(
                        bucket.label("bucket"),
                        _SKU_CURRENCY,
                        func.coalesce(func.sum(HistoricalSale.units_sold), 0).label("units"),
                        func.coalesce(func.sum(_GROSS_BEFORE_RETURNS), 0).label("gross"),
                        func.coalesce(func.sum(HistoricalSale.net_revenue), 0).label("net"),
                    )
                    .select_from(HistoricalSale)
                    .outerjoin(Sku, Sku.id == HistoricalSale.sku_id)
                    .where(
                        HistoricalSale.tenant_id == tenant_id,
                        HistoricalSale.industry == industry,
                        HistoricalSale.sale_time >= window_start,
                    )
                    .group_by(bucket, _SKU_CURRENCY)
                    .order_by(bucket)
                )
            ).fetchall()
            first_sale = await session.scalar(
                select(func.min(HistoricalSale.sale_time)).where(
                    HistoricalSale.tenant_id == tenant_id,
                    HistoricalSale.industry == industry,
                )
            )

        first_bucket = (
            _trunc_start(first_sale.astimezone(UTC), granularity) if first_sale else None
        )
        by_bucket: dict[datetime, list[Any]] = {}
        for r in rows:
            key = _day_start(r.bucket.replace(tzinfo=UTC) if r.bucket.tzinfo is None else r.bucket)
            by_bucket.setdefault(key, []).append(r)
        currencies = sorted({r.currency for r in rows if (r.gross or r.net)})
        mixed = len(currencies) > 1

        series: list[dict] = []
        cursor = window_start
        while cursor <= now:
            if first_bucket is None or cursor < first_bucket:
                series.append(
                    {
                        "bucket": cursor.date().isoformat(),
                        "units_sold": None,
                        "gross_revenue": None,
                        "net_revenue": None,
                        "revenue_by_currency": {},
                    }
                )
                cursor = _step(cursor, granularity)
                continue
            bucket_rows = by_bucket.get(_day_start(cursor), [])
            money = _money(bucket_rows)
            series.append(
                {
                    "bucket": cursor.date().isoformat(),
                    "units_sold": int(sum(r.units or 0 for r in bucket_rows)),
                    "gross_revenue": None if mixed else (money["gross_revenue"] or 0.0),
                    "net_revenue": None if mixed else (money["net_revenue"] or 0.0),
                    "revenue_by_currency": money["revenue_by_currency"],
                }
            )
            cursor = _step(cursor, granularity)

        return {
            "industry": ctx.code,
            "granularity": granularity,
            "lookback_days": lookback_days,
            "currency": currencies[0] if len(currencies) == 1 else None,
            "currencies": currencies,
            "first_sale_at": first_sale.astimezone(UTC).isoformat() if first_sale else None,
            # The bucket containing "now" is still filling up.
            "current_bucket": _trunc_start(now, granularity).date().isoformat(),
            "units_basis": "gross_units_sold_returns_not_netted",
            "series": series,
        }

    cache = get_response_cache(request)
    return await cache.get_or_set(
        tenant_id=tenant_id,
        name="sales:timeseries:v2",
        params={"industry": ctx.code, "granularity": granularity, "lookback_days": lookback_days},
        ttl_s=get_settings().api_cache_ttl_s,
        producer=_compute,
    )


# ── top products ─────────────────────────────────────────────────────────────


@router.get("/branches")
async def branch_sales(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    lookback_days: int = 365,
    granularity: Literal["day", "week", "month"] = "day",
) -> dict[str, Any]:
    """Compare explicit sale locations; never infer branches from regions."""
    lookback_days = max(1, min(lookback_days, 730))
    now = datetime.now(UTC)
    start = _trunc_start(now - timedelta(days=lookback_days), granularity)
    location = func.nullif(func.trim(HistoricalSale.location), "")

    async def _compute() -> dict[str, Any]:
        async with request.app.state.db.session(str(tenant_id)) as session:
            rows = (await session.execute(
                select(
                    location.label("name"), _SKU_CURRENCY,
                    func.sum(HistoricalSale.units_sold).label("units"),
                    func.sum(_GROSS_BEFORE_RETURNS).label("gross"),
                    func.sum(HistoricalSale.net_revenue).label("net"),
                    func.count(_GROSS_BEFORE_RETURNS).label("gross_count"),
                    func.count().label("records"),
                )
                .select_from(HistoricalSale)
                .outerjoin(Sku, (Sku.id == HistoricalSale.sku_id) & (Sku.tenant_id == tenant_id))
                .where(
                    HistoricalSale.tenant_id == tenant_id,
                    HistoricalSale.industry == IndustryCode(ctx.code),
                    HistoricalSale.sale_time >= start,
                    HistoricalSale.sale_time < now,
                )
                .group_by(location, _SKU_CURRENCY)
            )).all()
        grouped: dict[str, list[Any]] = {}
        unassigned = 0
        for row in rows:
            if row.name is None:
                unassigned += row.records
            else:
                grouped.setdefault(row.name, []).append(row)

        def _branch(name: str, group: list[Any]) -> dict[str, Any]:
            # NULL amounts are unavailable, not zero. Do not present a partial
            # currency total as the full branch revenue either.
            gross = {row.currency: float(row.gross) for row in group
                     if row.gross_count == row.records}
            currencies = {row.currency for row in group}
            complete = all(row.gross_count == row.records for row in group)
            if not complete:
                gross = {}
            return {
                "name": name,
                "units_sold": int(sum(row.units or 0 for row in group)),
                "currency": next(iter(currencies)) if len(currencies) == 1 else None,
                "gross_revenue": sum(gross.values()) if complete and len(currencies) == 1 else None,
                "revenue_by_currency": gross,
            }

        return {
            "industry": ctx.code,
            "period_start": start.isoformat(),
            "as_of": now.isoformat(),
            "lookback_days": lookback_days,
            "unassigned_records": unassigned,
            "branches": [_branch(name, group) for name, group in sorted(grouped.items())],
        }

    return await get_response_cache(request).get_or_set(
        tenant_id=tenant_id, name="sales:branches",
        params={"industry": ctx.code, "lookback_days": lookback_days, "granularity": granularity},
        ttl_s=get_settings().api_cache_ttl_s, producer=_compute,
    )


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
                        func.coalesce(func.sum(_GROSS_BEFORE_RETURNS), 0).label("gross"),
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
                        select(Sku.id, Sku.sku_code, Sku.currency, Product.name)
                        .join(Product, Product.id == Sku.product_id)
                        .where(Sku.tenant_id == tenant_id, Sku.id.in_(sku_ids))
                    )
                ).fetchall()
                names = {m.id: (m.sku_code, m.name, m.currency) for m in meta}

        unknown = ("—", "Unknown SKU", None)
        products = [
            {
                "sku_id": str(r.sku_id),
                "sku_code": names.get(r.sku_id, unknown)[0],
                "product_name": names.get(r.sku_id, unknown)[1],
                "units_sold": int(r.units or 0),
                "gross_revenue": float(r.gross or 0),
                "currency": names.get(r.sku_id, unknown)[2],
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
