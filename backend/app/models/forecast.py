from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import ForecastRunStatus, IndustryCode


class ForecastRun(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "forecast_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    run_name: Mapped[str | None] = mapped_column(Text)
    model_stack: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    horizon_weeks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    granularity: Mapped[str] = mapped_column(Text, nullable=False, default="weekly")
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ForecastRunStatus] = mapped_column(
        SAEnum(
            ForecastRunStatus,
            name="forecast_run_status",
            create_constraint=False,
            native_enum=False,
        ),
        nullable=False,
        default=ForecastRunStatus.pending,
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(Text)


class ForecastResult(Base):
    """Partitioned by forecast_date (RANGE). No FK constraints for same reason as HistoricalSale."""

    __tablename__ = "forecast_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    p10: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    p50: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    p90: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=__import__("sqlalchemy", fromlist=["func"]).func.now(),
        nullable=False,
    )

    __mapper_args__ = {"primary_key": [id, forecast_date]}
