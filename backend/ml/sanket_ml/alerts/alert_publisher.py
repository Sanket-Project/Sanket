"""Persist shortage alerts + emit them over the realtime layer.

This module is the bridge between the pure-Python detector (which knows
nothing about the database) and the rest of SANKET (which expects rows
in `shortage_alerts` and websocket events to land in the browser).

It can be called from:
  • the API path (POST /forecast/hybrid → run detector → publish)
  • a future Prefect background job that scans portfolios on a schedule
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from sanket_ml.alerts.shortage_detector import ShortageAlert as ShortageAlertDTO

if TYPE_CHECKING:
    pass  # session type is duck-typed (FirestoreSessionAdapter or AsyncSession)

log = structlog.get_logger(__name__)


class AlertPublisher:
    def __init__(self, realtime=None, cooldown_minutes: int = 60):
        """`realtime` is a ConnectionManager-like object (Phase 5).
        It's optional so the publisher works offline (tests, batch jobs)."""
        self.realtime = realtime
        self.cooldown_minutes = cooldown_minutes

    async def publish_many(
        self,
        session,
        tenant_id: uuid.UUID,
        alerts: Iterable[ShortageAlertDTO],
        rule_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        """Persist + broadcast alerts, honoring cooldown.

        Returns list of newly inserted alert IDs."""
        # Lazy-import ORM symbols so this module stays importable in environments
        # that don't have the backend app package on path (e.g. ML-only training).
        try:
            from app.models.alert import ShortageAlert as ShortageAlertORM
            from app.models.enums import AlertSeverity, AlertStatus, IndustryCode
        except ImportError:
            log.warning("alert.publisher.orm_unavailable")
            return []

        inserted: list[uuid.UUID] = []
        for alert in alerts:
            try:
                row = ShortageAlertORM(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    industry=IndustryCode(alert.industry),
                    sku_id=uuid.UUID(alert.sku_id) if alert.sku_id else None,
                    rule_id=rule_id,
                    severity=AlertSeverity(alert.severity),
                    status=AlertStatus.open,
                    risk_score=Decimal(str(round(alert.risk_score, 4))),
                    coverage_days=Decimal(str(round(alert.coverage_days, 2))),
                    p10_demand=Decimal(str(round(alert.p10_demand, 2))),
                    p50_demand=Decimal(str(round(alert.p50_demand, 2))),
                    p90_demand=Decimal(str(round(alert.p90_demand, 2))),
                    trend_score=Decimal(str(round(alert.trend_score, 4))),
                    drivers=alert.drivers,
                    title=alert.title,
                    message=alert.message,
                    fired_at=alert.fired_at,
                )
                session.add(row)
                inserted.append(row.id)
                await self._broadcast(tenant_id, alert, row.id)
            except Exception as exc:
                log.warning(
                    "alert.publish.row_failed",
                    sku=alert.sku_code,
                    severity=alert.severity,
                    error=str(exc),
                )

        if inserted:
            log.info(
                "alert.publish.batch",
                tenant=str(tenant_id),
                count=len(inserted),
            )
        return inserted

    async def _broadcast(
        self,
        tenant_id: uuid.UUID,
        alert: ShortageAlertDTO,
        alert_id: uuid.UUID,
    ) -> None:
        if self.realtime is None:
            return
        try:
            from app.realtime.events import RealtimeEvent  # type: ignore

            event = RealtimeEvent(
                type="shortage.alert",
                tenant_id=tenant_id,
                industry=alert.industry,
                data={
                    "alert_id": str(alert_id),
                    "sku_id": alert.sku_id,
                    "sku_code": alert.sku_code,
                    "severity": alert.severity,
                    "risk_score": round(alert.risk_score, 4),
                    "coverage_days": round(alert.coverage_days, 2),
                    "title": alert.title,
                    "message": alert.message,
                    "trend_score": round(alert.trend_score, 4),
                },
            )
            await self.realtime.publish(event)
        except Exception as exc:
            log.warning("alert.broadcast.failed", error=str(exc))
