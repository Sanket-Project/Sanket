from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPrimaryKey
from app.models.enums import IndustryCode, TrendSignalKind, TrendSignalSource


class TrendSignal(UUIDPrimaryKey, Base):
    """A single normalized external signal observation.

    `tenant_id` is nullable — most signals are global (FRED, Google Trends),
    visible to all tenants of the matching industry via RLS.
    """

    __tablename__ = "trend_signals"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    source: Mapped[TrendSignalSource] = mapped_column(
        SAEnum(TrendSignalSource, name="trend_signal_source"), nullable=False
    )
    kind: Mapped[TrendSignalKind] = mapped_column(
        SAEnum(TrendSignalKind, name="trend_signal_kind"), nullable=False
    )
    series_key: Mapped[str] = mapped_column(Text, nullable=False)
    category_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    sku_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    region: Mapped[str | None] = mapped_column(Text)
    raw_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    normalized_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("1.0")
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class HybridForecastRun(UUIDPrimaryKey, Base):
    """Audit row for each /forecast/hybrid call.

    Stores the trend score + adjuster params used, plus the scenario set
    so the UI can render past hybrid runs without re-computing."""

    __tablename__ = "hybrid_forecast_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    base_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    horizon_weeks: Mapped[int] = mapped_column(nullable=False)
    # Job lifecycle: pending → running → completed | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    request_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Compute outputs — null until the job finishes.
    trend_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    signal_volatility: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    alpha: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    beta: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    scenarios: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    drivers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Full HybridForecastOut payload, so status polling / history avoid recompute.
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
