"""Uploaded sales and catalogue-matched external interest, with bounded responses.

The database aggregates sales; no sales histories or 25k-SKU lists travel to the
browser. Existing public observations are reused only after catalogue matching.
No remote service is called on this read path.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import case, distinct, func, or_, select, text

from app.models.enums import IndustryCode, TrendSignalKind, TrendSignalSource
from app.models.location import Location
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.models.trend import TrendSignal
from app.services.external_signals.regional_demand_connector import (
    RegionalDemandConnector,
    region_metadata,
)


def _scope(tenant_id, industry):
    return [
        Sku.tenant_id == tenant_id,
        Sku.industry == IndustryCode(industry),
        Sku.is_active.is_(True),
        Product.tenant_id == tenant_id,
        Product.industry == IndustryCode(industry),
    ]


async def catalogue_options(
    session, tenant_id, industry, *, kind, q, limit, offset, product_id=None
):
    scope = _scope(tenant_id, industry)
    if product_id:
        scope.append(Product.id == product_id)
    if q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        needle = f"%{escaped}%"
        scope.append(
            or_(
                Sku.sku_code.ilike(needle),
                Product.name.ilike(needle),
                Product.category.ilike(needle),
            )
        )
    if kind == "product":
        base = (
            select(Product.id, Product.name, Product.category)
            .join(Sku, Sku.product_id == Product.id)
            .where(*scope)
            .distinct()
        )
        total = await session.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            await session.execute(
                base.order_by(Product.name, Product.id).offset(offset).limit(limit)
            )
        ).all()
        items = [
            {
                "id": str(r.id),
                "label": r.name,
                "kind": kind,
                "product_id": str(r.id),
                "product_name": r.name,
                "sku_code": None,
                "category": r.category,
            }
            for r in rows
        ]
    else:
        base = (
            select(
                Sku.id, Sku.sku_code, Product.id.label("product_id"), Product.name, Product.category
            )
            .join(Product, Product.id == Sku.product_id)
            .where(*scope)
        )
        total = await session.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            await session.execute(base.order_by(Sku.sku_code, Sku.id).offset(offset).limit(limit))
        ).all()
        items = [
            {
                "id": str(r.id),
                "label": f"{r.sku_code} · {r.name}",
                "kind": kind,
                "product_id": str(r.product_id),
                "product_name": r.name,
                "sku_code": r.sku_code,
                "category": r.category,
            }
            for r in rows
        ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


def _normal(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _change(current, previous):
    return round((current - previous) / previous * 100, 1) if previous > 0 else None


async def company_trends(
    session,
    tenant_id: uuid.UUID,
    industry: str,
    *,
    days=28,
    product_id=None,
    sku_id=None,
    state=None,
    district=None,
):
    scope = _scope(tenant_id, industry)
    counts = (
        await session.execute(
            select(func.count(distinct(Product.id)), func.count(Sku.id))
            .select_from(Sku)
            .join(Product)
            .where(*scope)
        )
    ).one()
    catalogue = {"product_count": counts[0], "sku_count": counts[1]}
    if product_id:
        scope.append(Product.id == product_id)
    if sku_id:
        scope.append(Sku.id == sku_id)
    selected = select(Sku.id).join(Product).where(*scope)
    sale_scope = [
        HistoricalSale.tenant_id == tenant_id,
        HistoricalSale.industry == IndustryCode(industry),
        HistoricalSale.sku_id.in_(selected),
    ]
    latest = await session.scalar(select(func.max(HistoricalSale.sale_time)).where(*sale_scope))
    end = latest.date() if latest else datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    previous_start = start - timedelta(days=days)
    bounds = {
        "days": days,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "previous_start": previous_start.isoformat(),
    }
    empty_sales = {
        "status": "no_history",
        "current_units": None,
        "previous_units": None,
        "change_pct": None,
        "observations": 0,
        "as_of": None,
        "series": [],
        "leaders": [],
    }
    geographic_missing = False
    if state or district:
        location_scope = [Location.tenant_id == tenant_id]
        if state:
            location_scope.append(
                func.lower(Location.attributes["state"].astext) == state.casefold()
            )
        if district:
            location_scope.append(
                func.lower(Location.attributes["district"].astext) == district.casefold()
            )
        codes = select(Location.code).where(*location_scope)
        mapped = await session.scalar(
            select(func.count()).select_from(Location).where(*location_scope)
        )
        geographic_missing = not mapped
        sale_scope.append(func.lower(func.trim(HistoricalSale.location)).in_(codes))
    sales = dict(empty_sales)
    if geographic_missing:
        sales["status"] = "unmapped_geography"
    elif latest:
        current_start = datetime.combine(start, time.min, UTC)
        lower = datetime.combine(previous_start, time.min, UTC)
        upper = datetime.combine(end + timedelta(days=1), time.min, UTC)
        current = HistoricalSale.sale_time >= current_start
        period_scope = [
            *sale_scope,
            HistoricalSale.sale_time >= lower,
            HistoricalSale.sale_time < upper,
        ]
        result = (
            await session.execute(
                select(
                    func.coalesce(func.sum(case((current, HistoricalSale.units_sold), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((~current, HistoricalSale.units_sold), else_=0)), 0
                    ),
                    func.count(),
                    func.max(HistoricalSale.sale_time),
                ).where(*period_scope)
            )
        ).one()
        if result[2]:
            series = (
                await session.execute(
                    select(
                        func.date(HistoricalSale.sale_time).label("date"),
                        func.sum(HistoricalSale.units_sold).label("units"),
                    )
                    .where(*period_scope, current)
                    .group_by(func.date(HistoricalSale.sale_time))
                    .order_by(func.date(HistoricalSale.sale_time))
                )
            ).all()
            current_units = func.coalesce(
                func.sum(case((current, HistoricalSale.units_sold), else_=0)), 0
            )
            prior_units = func.coalesce(
                func.sum(case((~current, HistoricalSale.units_sold), else_=0)), 0
            )
            leaders = (
                await session.execute(
                    select(Sku.id, Sku.sku_code, Product.name, current_units, prior_units)
                    .select_from(HistoricalSale)
                    .join(Sku, Sku.id == HistoricalSale.sku_id)
                    .join(Product, Product.id == Sku.product_id)
                    .where(*period_scope, *scope)
                    .group_by(Sku.id, Sku.sku_code, Product.name)
                    .order_by(current_units.desc(), Sku.sku_code)
                    .limit(20)
                )
            ).all()
            sales = {
                "status": "available",
                "current_units": result[0],
                "previous_units": result[1],
                "change_pct": _change(result[0], result[1]),
                "observations": result[2],
                "as_of": result[3].isoformat(),
                "series": [{"date": str(r.date), "units": r.units} for r in series],
                "leaders": [
                    {
                        "sku_id": str(r.id),
                        "sku_code": r.sku_code,
                        "product_name": r.name,
                        "current_units": r[3],
                        "previous_units": r[4],
                        "change_pct": _change(r[3], r[4]),
                    }
                    for r in leaders
                ],
            }
    external = (
        await _external(session, tenant_id, industry, scope, state, district) if counts[1] else []
    )
    return {
        "catalogue": catalogue,
        "period": bounds,
        "sales": sales,
        "external": {
            "status": "available" if external else "no_matches",
            "as_of": max((x["captured_at"] for x in external), default=None),
            "items": external,
        },
    }


async def _external(session, tenant_id, industry, scope, state, district):
    # Search interests, rather than macro/weather scores, have catalogue terms.
    # This read is a bounded 30-day/latest-1000-observation window, not a claim
    # to cover every market term. A tenant refresh prioritizes current terms.
    observations = (
        (
            await session.execute(
                select(TrendSignal)
                .where(
                    TrendSignal.industry == IndustryCode(industry),
                    or_(TrendSignal.tenant_id.is_(None), TrendSignal.tenant_id == tenant_id),
                    TrendSignal.kind == TrendSignalKind.search_interest,
                    TrendSignal.source != TrendSignalSource.synthetic,
                    TrendSignal.captured_at >= datetime.now(UTC) - timedelta(days=30),
                )
                .order_by(TrendSignal.captured_at.desc())
                .limit(1000)
            )
        )
        .scalars()
        .all()
    )
    terms = {
        _normal(
            (s.payload or {}).get("product")
            or (s.payload or {}).get("keyword")
            or (s.payload or {}).get("query")
            or ""
        )
        for s in observations
    }
    terms.discard("")
    matches = {term: set() for term in terms}
    if not terms:
        return []
    # Stream small catalogue metadata chunks; variant duplication cannot multiply
    # either remote requests or response rows. Only exact word phrases match.
    rows = await session.stream(
        select(Product.name, Product.category, Sku.description)
        .select_from(Sku)
        .join(Product)
        .where(*scope)
        .execution_options(yield_per=512)
    )
    async for name, category, description in rows:
        for value in (name, category, description):
            words = _normal(value or "").split()
            for i in range(len(words)):
                for size in range(1, min(8, len(words) - i) + 1):
                    phrase = " ".join(words[i : i + size])
                    if phrase in matches and len(matches[phrase]) < 8:
                        matches[phrase].add(name)
    out, seen = [], set()
    for signal in observations:
        payload = signal.payload or {}
        term = payload.get("product") or payload.get("keyword") or payload.get("query") or ""
        matched = matches.get(_normal(term))
        if not matched or payload.get("synthetic") or payload.get("is_synthetic"):
            continue
        geo = region_metadata(payload.get("city") or payload.get("state") or "")
        level = payload.get("geography_level") or geo["geography_level"]
        # Old provider rows sometimes stored a state in `city`. Correct on read.
        state_name = (
            geo["state"]
            if geo["geography_level"] == "state"
            else payload.get("state") or geo["state"]
        )
        city = None if geo["geography_level"] == "state" else payload.get("city")
        district_name = payload.get("district")
        if district_name:
            level = "district"
        if state and _normal(state_name) != _normal(state):
            continue
        if district and _normal(district_name) != _normal(district):
            continue
        raw = payload.get("relative_search_interest")
        if raw is None and signal.source.value == "google_trends":
            raw = signal.raw_value
        try:
            interest = float(raw) if raw is not None and 0 <= float(raw) <= 100 else None
        except (ValueError, TypeError):
            interest = None
        key = (_normal(term), signal.source.value, state_name, city, district_name)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": str(signal.id),
                "term": term,
                "source": signal.source.value,
                "captured_at": signal.captured_at.isoformat(),
                "relative_interest": interest,
                "region": signal.region,
                "state": state_name,
                "district": district_name,
                "city": city,
                "geography_level": level if level in {"state", "city", "district"} else "unknown",
                "matched_products": sorted(matched),
            }
        )
        if len(out) >= 50:
            break
    return out


async def refresh_company_interest(db, tenant_id, industry):
    """Background collection: at most eight deduped catalogue terms per sweep.

    The same transaction-scoped lock gates workers and the no-Redis local
    fallback. The session uses the app role/RLS and writes only this tenant.
    Fresh results are reused for fifteen minutes, including across replicas.
    """
    tid = uuid.UUID(str(tenant_id))
    async with db.session(str(tid)) as session:
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"company-interest:{tid}:{industry}"},
        )
        if not locked:
            return {"status": "running", "persisted": 0}
        latest = await session.scalar(
            select(func.max(TrendSignal.captured_at)).where(
                TrendSignal.tenant_id == tid,
                TrendSignal.industry == IndustryCode(industry),
                TrendSignal.payload["catalogue_collection"].astext == "true",
            )
        )
        if latest and latest >= datetime.now(UTC) - timedelta(minutes=15):
            return {"status": "fresh", "persisted": 0}
        scope = _scope(tid, industry)
        # Aggregate before loading: thousands of size/color variants become a
        # few product/category terms. No literal internal SKU codes are queried.
        category_rows = (
            await session.execute(
                select(Product.category, func.count(Sku.id).label("n"))
                .select_from(Sku)
                .join(Product)
                .where(*scope)
                .group_by(Product.category)
                .order_by(func.count(Sku.id).desc(), Product.category)
                .limit(8)
            )
        ).all()
        product_rows = (
            await session.execute(
                select(Product.name, Product.category, func.count(Sku.id).label("n"))
                .select_from(Sku)
                .join(Product)
                .where(*scope)
                .group_by(Product.name, Product.category)
                .order_by(func.count(Sku.id).desc(), Product.name)
                .limit(8)
            )
        ).all()
        terms, seen = [], set()
        candidates = [(r.category, r.category) for r in category_rows[:4]] + [
            (r.name, r.category) for r in product_rows
        ]
        candidates += [(r.category, r.category) for r in category_rows[4:]]
        generic = {"unknown", "other", "uncategorized", "imported products", "products", "general"}
        for value, category in candidates:
            term = _normal(value)
            if term and term not in seen and term not in generic and len(term) <= 80:
                seen.add(term)
                terms.append((term, category or value))
            if len(terms) == 8:
                break
        if not terms:
            return {"status": "no_catalogue_terms", "persisted": 0}
        samples = await asyncio.to_thread(
            RegionalDemandConnector()._fetch_distribution, industry, terms
        )
        persisted = 0
        for sample in samples[:240]:
            if sample.payload.get("synthetic") or sample.payload.get("is_synthetic"):
                continue
            session.add(
                TrendSignal(
                    tenant_id=tid,
                    industry=IndustryCode(industry),
                    source=TrendSignalSource(sample.source),
                    kind=TrendSignalKind(sample.kind),
                    series_key=sample.series_key,
                    category_tags=sample.category_tags,
                    sku_tags=sample.sku_tags,
                    region=sample.region,
                    raw_value=Decimal(str(sample.raw_value))
                    if sample.raw_value is not None
                    else None,
                    normalized_score=Decimal(str(sample.normalized_score)),
                    confidence=Decimal(str(sample.confidence)),
                    captured_at=sample.captured_at,
                    payload={**sample.payload, "catalogue_collection": True},
                )
            )
            persisted += 1
        return {
            "status": "completed" if persisted else "no_evidence",
            "persisted": persisted,
            "terms_requested": len(terms),
        }
