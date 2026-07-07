from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import MeterKind, Plan, Subscription, UsageEvent
from app.realtime import RealtimeEvent, get_connection_manager
from app.realtime.events import EVENT_USAGE_QUOTA, UsageQuotaData

log = structlog.get_logger(__name__)


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    meter: MeterKind,
    quantity: float | Decimal,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append-only usage event. Swallows errors so business logic never blocks."""
    try:
        await session.execute(
            text(
                """
                INSERT INTO usage_events (tenant_id, meter, quantity, idempotency_key, metadata)
                VALUES (:tid, :meter::meter_kind, :qty, :key, :meta::jsonb)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "tid": str(tenant_id),
                "meter": meter.value,
                "qty": float(quantity),
                "key": idempotency_key,
                "meta": _to_json(metadata or {}),
            },
        )
    except Exception as exc:
        log.error("usage.record.failed", meter=meter.value, error=str(exc))


async def current_period_usage(
    session: AsyncSession, *, tenant_id: uuid.UUID, meter: MeterKind
) -> Decimal:
    """Sum the meter over the active subscription period."""
    sub = await _active_subscription(session, tenant_id)
    if sub is None:
        # No subscription → bill against rolling 30 days
        start = datetime.now(tz=UTC) - timedelta(days=30)
    else:
        start = sub.current_period_start
    result = await session.execute(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.meter == meter,
            UsageEvent.occurred_at >= start,
        )
    )
    return Decimal(result.scalar() or 0)


async def quota_check(
    session: AsyncSession, *, tenant_id: uuid.UUID, meter: MeterKind
) -> tuple[float, float, str | None]:
    """Return (used, limit, severity) — severity is None | 'warning' | 'exceeded'."""
    sub = await _active_subscription(session, tenant_id)
    if sub is None:
        return 0.0, float("inf"), None
    plan = await session.get(Plan, sub.plan_id)
    if plan is None:
        return 0.0, float("inf"), None
    limit = float(plan.included_quotas.get(meter.value, float("inf")))
    used = float(await current_period_usage(session, tenant_id=tenant_id, meter=meter))
    pct = used / limit if limit > 0 else 0.0
    severity: str | None = None
    if pct >= 1.0:
        severity = "exceeded"
    elif pct >= 0.8:
        severity = "warning"
    return used, limit, severity


async def emit_quota_alerts(
    session: AsyncSession, *, tenant_id: uuid.UUID, meter: MeterKind
) -> None:
    used, limit, severity = await quota_check(session, tenant_id=tenant_id, meter=meter)
    if severity is None:
        return
    event = RealtimeEvent(
        type=EVENT_USAGE_QUOTA,
        tenant_id=tenant_id,
        data=UsageQuotaData(
            meter=meter.value,
            used=used,
            limit=limit,
            pct=used / limit if limit > 0 else 0.0,
            severity=severity,  # type: ignore[arg-type]
        ).model_dump(),
    )
    await get_connection_manager().publish(event)


async def rollup_daily(session: AsyncSession, day: date | None = None) -> int:
    """Aggregate usage_events → usage_rollups_daily for a given day. Idempotent."""
    day = day or (date.today() - timedelta(days=1))
    res = await session.execute(
        text(
            """
            INSERT INTO usage_rollups_daily (tenant_id, meter, day, quantity)
            SELECT tenant_id, meter, :day::date, COALESCE(SUM(quantity), 0)
            FROM usage_events
            WHERE occurred_at >= :day::date
              AND occurred_at <  (:day::date + INTERVAL '1 day')
            GROUP BY tenant_id, meter
            ON CONFLICT (tenant_id, meter, day) DO UPDATE
              SET quantity = EXCLUDED.quantity
            """
        ),
        {"day": day},
    )
    log.info("usage.rollup.done", day=str(day), rows=getattr(res, "rowcount", 0) or 0)
    return getattr(res, "rowcount", 0) or 0


# ── helpers ──
async def _active_subscription(session: AsyncSession, tenant_id: uuid.UUID) -> Subscription | None:
    res = await session.execute(
        select(Subscription)
        .where(
            Subscription.tenant_id == tenant_id,
            Subscription.status.in_(("trialing", "active", "past_due")),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


def _to_json(d: dict) -> str:
    import json

    return json.dumps(d, default=str)
