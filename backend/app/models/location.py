"""Store / warehouse network and per-location forecasts (location spec §3–§4)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, UniqueConstraint
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
