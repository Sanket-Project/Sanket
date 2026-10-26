"""Store / warehouse network and per-location forecasts (location spec §3–§4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, SmallInteger, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import LocationKind


class Location(UUIDPrimaryKey, TimestampMixin, Base):
    """One store or warehouse. ``code`` is ``lower(trim(raw))`` of the text that
    sales and inventory rows carry in their ``location`` column."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_locations_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[LocationKind] = mapped_column(
        SAEnum(LocationKind, name="location_kind", create_constraint=False, native_enum=False),
        nullable=False,
        default=LocationKind.unconfirmed,
    )
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL")
    )
    lead_time_days_from_parent: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class LocationForecastResult(Base):
    """Partitioned by forecast_date (RANGE); no FK on sku/location, like ForecastResult."""

    __tablename__ = "location_forecast_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    p10: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    p50: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    p90: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    share: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    share_basis: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="share_split_v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __mapper_args__ = {"primary_key": [id, forecast_date]}
