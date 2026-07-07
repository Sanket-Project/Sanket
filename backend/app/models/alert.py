from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import AlertSeverity, AlertStatus, IndustryCode


class AlertRule(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "industry", "rule_name", name="uq_alert_rules_tenant_name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    rule_name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    warn_coverage_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    critical_coverage_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    trend_weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.30")
    )
    p90_weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.40")
    )
    inventory_weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.30")
    )
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    notify_webhook: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_websocket: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ShortageAlert(UUIDPrimaryKey, Base):
    __tablename__ = "shortage_alerts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    sku_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id")
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SAEnum(AlertSeverity, name="alert_severity"), nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus, name="alert_status"), nullable=False, default=AlertStatus.open
    )
    risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    coverage_days: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    p10_demand: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    p50_demand: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    p90_demand: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    trend_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    drivers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
