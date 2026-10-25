"""Database-facing side of the decision engine.

Pulls the real inputs — latest completed forecast run, weekly sales history,
recorded stock, SKU economics, open shortage alerts — feeds them to the pure
:mod:`app.services.decision_engine`, and persists the result.

Nothing here fabricates a number. If a tenant has no completed forecast run the
builder returns an empty result and says why, because a recommendation invented
from a placeholder forecast is worse than no recommendation at all.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import week_bucket
from app.models.alert import ShortageAlert
from app.models.enums import AlertStatus, DecisionStatus, IndustryCode
from app.models.forecast import ForecastResult, ForecastRun
from app.models.product import Sku
from app.models.recommendation import Recommendation
from app.models.sales import HistoricalSale
from app.services.decision_engine import (
    DEFAULT_LEAD_TIME_DAYS,
    Decision,
    DemandBand,
    PolicyConfig,
    SkuEconomics,
    decide,
)
from app.services.forecast_confidence import (
    ConfidenceScore,
    features_from_series,
    score_confidence,
)
from app.services.inventory import current_levels

log = structlog.get_logger(__name__)

HISTORY_WEEKS = 104
#: Hard ceiling on SKUs scored per run. Planners act on a queue, not a catalog,
#: and the whole point is to hand them the few decisions that matter.
MAX_SKUS = 500


@dataclass(frozen=True, slots=True)
class BuildResult:
    decisions: list[Decision]
    run_id: uuid.UUID | None
    skus_evaluated: int
    reason: str | None = None  # populated when nothing could be produced


def load_policy(tenant_settings: dict | None) -> PolicyConfig:
    """Read the tenant's ordering policy out of ``Tenant.settings['decisions']``.

    Defaults are deliberately conservative: 97% service level is the number most
    distributors quote to their customers, and a 28-day review cycle matches a
    monthly PO run.
    """
    raw = (tenant_settings or {}).get("decisions") or {}
    base = PolicyConfig()
    try:
        return PolicyConfig(
            service_level=float(raw.get("service_level", base.service_level)),
            review_period_days=int(raw.get("review_period_days", base.review_period_days)),
            holding_cost_pct=float(raw.get("holding_cost_pct", base.holding_cost_pct)),
            min_confidence_to_act=int(
                raw.get("min_confidence_to_act", base.min_confidence_to_act)
            ),
        )
    except (TypeError, ValueError):
        log.warning("decisions.policy.invalid", raw=raw)
        return base


async def latest_completed_run(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> ForecastRun | None:
    return await session.scalar(
        select(ForecastRun)
        .where(
            ForecastRun.tenant_id == tenant_id,
            ForecastRun.industry == industry,
            ForecastRun.status == "completed",
        )
        .order_by(ForecastRun.completed_at.desc())
        .limit(1)
    )


async def forecast_bands(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> dict[uuid.UUID, DemandBand]:
    """Weekly p10/p50/p90 per SKU, ordered forward from the earliest date.

    Rows for the same (sku, date) from several models are averaged — the fusion
    layer already picks a winner where it can, and averaging is the honest
    fallback when it has not.
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


async def weekly_history(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    sku_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[list[float], datetime | None]]:
    """Dense weekly demand per SKU plus the last sale timestamp.

    Weeks with no sales are filled with explicit zeros — the confidence scorer
    keys off the zero ratio, which a sparse series would hide entirely.
    """
    if not sku_ids:
        return {}

    cutoff = datetime.now(UTC) - timedelta(weeks=HISTORY_WEEKS)
    week = week_bucket(HistoricalSale.sale_time).label("week")
    rows = (
        await session.execute(
            select(
                HistoricalSale.sku_id,
                week,
                func.sum(HistoricalSale.units_sold).label("units"),
                func.max(HistoricalSale.sale_time).label("last_sale"),
            )
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sku_id.in_(sku_ids),
                HistoricalSale.sale_time >= cutoff,
            )
            .group_by(HistoricalSale.sku_id, week)
            .order_by(HistoricalSale.sku_id, week)
        )
    ).fetchall()

    per_sku: dict[uuid.UUID, dict[datetime, float]] = {}
    last_sale: dict[uuid.UUID, datetime] = {}
    for r in rows:
        per_sku.setdefault(r.sku_id, {})[r.week] = float(r.units or 0)
        prev = last_sale.get(r.sku_id)
        if r.last_sale is not None and (prev is None or r.last_sale > prev):
            last_sale[r.sku_id] = r.last_sale

    out: dict[uuid.UUID, tuple[list[float], datetime | None]] = {}
    for sku_id, weeks in per_sku.items():
        first = min(weeks)
        last = max(weeks)
        dense: list[float] = []
        cursor = first
        while cursor <= last:
            dense.append(weeks.get(cursor, 0.0))
            cursor = cursor + timedelta(weeks=1)
        out[sku_id] = (dense, last_sale.get(sku_id))
    return out


async def _open_alerts(
    session: AsyncSession, tenant_id: uuid.UUID, industry: IndustryCode
) -> dict[uuid.UUID, uuid.UUID]:
    rows = (
        await session.execute(
            select(ShortageAlert.sku_id, ShortageAlert.id)
            .where(
                ShortageAlert.tenant_id == tenant_id,
                ShortageAlert.industry == industry,
                ShortageAlert.status.in_([AlertStatus.open, AlertStatus.acknowledged]),
                ShortageAlert.sku_id.isnot(None),
            )
            .order_by(ShortageAlert.fired_at.desc())
        )
    ).fetchall()
    # Newest alert wins per SKU.
    mapping: dict[uuid.UUID, uuid.UUID] = {}
    for sku_id, alert_id in rows:
        mapping.setdefault(sku_id, alert_id)
    return mapping


def confidence_for(
    band: DemandBand,
    history: tuple[list[float], datetime | None] | None,
    run: ForecastRun,
) -> tuple[ConfidenceScore, float | None]:
    weekly, last_sale = history or ([], None)
    days_since = None
    if last_sale is not None:
        ref = last_sale if last_sale.tzinfo else last_sale.replace(tzinfo=UTC)
        days_since = max(0, (datetime.now(UTC) - ref).days)

    metrics = run.metrics or {}
    wape = metrics.get("wape") if isinstance(metrics, dict) else None
    models = run.model_stack or []

    features = features_from_series(
        weekly_units=weekly,
        days_since_last_sale=days_since,
        p10_sum=sum(band.p10),
        p50_sum=sum(band.p50),
        p90_sum=sum(band.p90),
        backtest_wape=float(wape) if isinstance(wape, (int, float)) else None,
        models_in_ensemble=max(1, len(models)),
        zero_shot=any("chronos" in str(m).lower() or "zero_shot" in str(m).lower() for m in models),
    )
    trailing = (sum(weekly[-8:]) / len(weekly[-8:])) if len(weekly) >= 4 else None
    return score_confidence(features), trailing


async def build_decisions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    policy: PolicyConfig,
    sku_ids: list[uuid.UUID] | None = None,
) -> BuildResult:
    """Compute (but do not persist) every decision for a tenant + industry."""
    ind = IndustryCode(industry)

    run = await latest_completed_run(session, tenant_id, ind)
    if run is None:
        return BuildResult(
            decisions=[],
            run_id=None,
            skus_evaluated=0,
            reason=(
                "No completed forecast run yet. Generate a forecast first — "
                "recommendations are derived from it, never estimated."
            ),
        )

    bands = await forecast_bands(session, tenant_id, run.id)
    if sku_ids:
        wanted = set(sku_ids)
        bands = {k: v for k, v in bands.items() if k in wanted}
    if not bands:
        return BuildResult(
            decisions=[],
            run_id=run.id,
            skus_evaluated=0,
            reason="The latest forecast run produced no SKU-level results.",
        )

    ids = list(bands)[:MAX_SKUS]
    sku_rows = (
        await session.execute(
            select(Sku).where(
                Sku.tenant_id == tenant_id,
                Sku.industry == ind,
                Sku.id.in_(ids),
                Sku.is_active.is_(True),
            )
        )
    ).scalars().all()
    skus = {s.id: s for s in sku_rows}
    if not skus:
        return BuildResult(
            decisions=[], run_id=run.id, skus_evaluated=0,
            reason="No active SKUs matched the latest forecast run.",
        )

    stock = await current_levels(
        session, tenant_id=tenant_id, industry=industry, sku_ids=list(skus)
    )
    history = await weekly_history(session, tenant_id, ind, list(skus))

    decisions: list[Decision] = []
    for sku_id, sku in skus.items():
        band = bands[sku_id]
        snapshot = stock.get(str(sku_id))
        confidence, trailing = confidence_for(band, history.get(sku_id), run)

        econ = SkuEconomics(
            sku_id=str(sku_id),
            sku_code=sku.sku_code,
            on_hand_units=float(snapshot.on_hand_units) if snapshot else 0.0,
            reserved_units=float(snapshot.reserved_units) if snapshot else 0.0,
            inbound_units=float(snapshot.inbound_units) if snapshot else 0.0,
            lead_time_days=int(sku.lead_time_days or DEFAULT_LEAD_TIME_DAYS),
            moq=int(sku.moq or 1),
            unit_cost=float(sku.unit_cost or 0),
            unit_price=float(sku.unit_price or 0),
            currency=sku.currency or "INR",
            configured_safety_stock=int(sku.safety_stock or 0),
        )
        decisions.extend(
            decide(sku=econ, band=band, confidence=confidence, policy=policy,
                   trailing_weekly_mean=trailing)
        )

    _sort(decisions)
    return BuildResult(decisions=decisions, run_id=run.id, skus_evaluated=len(skus))


_URGENCY_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def _sort(decisions: list[Decision]) -> None:
    """Most urgent first, then by money at stake — the order a planner works in."""
    decisions.sort(
        key=lambda d: (
            _URGENCY_RANK.get(d.urgency, 9),
            -float(d.economics.get("revenue_protected") or d.economics.get("capital_locked") or 0),
        )
    )


async def persist_decisions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    run_id: uuid.UUID | None,
    decisions: list[Decision],
    alerts: dict[uuid.UUID, uuid.UUID] | None = None,
    ttl_days: int = 14,
) -> list[Recommendation]:
    """Replace the open queue with a freshly computed one.

    Open rows are expired rather than deleted so the ROI ledger keeps a complete
    history of what was offered, and accepted/dismissed rows are never touched —
    those are the user's decisions, not ours to rewrite.
    """
    ind = IndustryCode(industry)
    now = datetime.now(UTC)

    existing = (
        await session.execute(
            select(Recommendation).where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.industry == ind,
                Recommendation.status == DecisionStatus.open,
            )
        )
    ).scalars().all()
    for row in existing:
        row.status = DecisionStatus.expired

    # Flush the supersede before inserting, so the partial unique index on
    # (tenant, sku, kind) WHERE status='open' does not trip on the old rows.
    await session.flush()

    alerts = alerts or {}
    created: list[Recommendation] = []
    for d in decisions:
        sku_uuid = uuid.UUID(d.sku_id)
        rec = Recommendation(
            tenant_id=tenant_id,
            industry=ind,
            sku_id=sku_uuid,
            run_id=run_id,
            kind=d.kind,
            status=DecisionStatus.open,
            urgency=d.urgency,
            headline=d.headline,
            recommended_units=d.recommended_units,
            baseline_units=d.baseline_units,
            confidence=d.confidence,
            confidence_band=d.confidence_band,
            unit_cost=Decimal(str(d.inputs.get("unit_cost", 0) or 0)),
            unit_price=Decimal(str(d.inputs.get("unit_price", 0) or 0)),
            currency=str(d.economics.get("currency") or "INR"),
            reasons=[r.as_dict() for r in d.reasons],
            economics=d.economics,
            inputs=d.inputs,
            linked_alert_id=alerts.get(sku_uuid),
            expires_at=now + timedelta(days=ttl_days),
        )
        session.add(rec)
        created.append(rec)

    await session.flush()
    log.info(
        "decisions.persisted",
        tenant_id=str(tenant_id),
        industry=industry,
        superseded=len(existing),
        created=len(created),
    )
    return created


async def refresh(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    industry: str,
    tenant_settings: dict | None,
) -> tuple[BuildResult, list[Recommendation]]:
    """Recompute and persist the decision queue in one call."""
    policy = load_policy(tenant_settings)
    result = await build_decisions(
        session, tenant_id=tenant_id, industry=industry, policy=policy
    )
    if not result.decisions:
        return result, []
    alerts = await _open_alerts(session, tenant_id, IndustryCode(industry))
    rows = await persist_decisions(
        session,
        tenant_id=tenant_id,
        industry=industry,
        run_id=result.run_id,
        decisions=result.decisions,
        alerts=alerts,
    )
    return result, rows


def serialize(rec: Recommendation, *, sku_code: str | None = None) -> dict[str, Any]:
    return {
        "id": str(rec.id),
        "sku_id": str(rec.sku_id),
        "sku_code": sku_code,
        "kind": str(rec.kind),
        "status": str(rec.status),
        "urgency": str(rec.urgency),
        "headline": rec.headline,
        "recommended_units": rec.recommended_units,
        "baseline_units": rec.baseline_units,
        "accepted_units": rec.accepted_units,
        "confidence": rec.confidence,
        "confidence_band": rec.confidence_band,
        "currency": rec.currency,
        "unit_cost": float(rec.unit_cost or 0),
        "unit_price": float(rec.unit_price or 0),
        "reasons": rec.reasons,
        "economics": rec.economics,
        "inputs": rec.inputs,
        "linked_alert_id": str(rec.linked_alert_id) if rec.linked_alert_id else None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "decided_at": rec.decided_at.isoformat() if rec.decided_at else None,
        "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
    }
