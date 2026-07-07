from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import IndustryCode, SignalStatus, SignalType

try:
    from pgvector.sqlalchemy import Vector

    _VECTOR_AVAILABLE = True
except ImportError:
    _VECTOR_AVAILABLE = False
    Vector = None  # type: ignore[assignment,misc]


class ExternalSignal(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "external_signals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    signal_type: Mapped[SignalType] = mapped_column(
        SAEnum(SignalType, name="signal_type"), nullable=False
    )
    status: Mapped[SignalStatus] = mapped_column(
        SAEnum(SignalStatus, name="signal_status"), nullable=False, default=SignalStatus.pending
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    region: Mapped[str | None] = mapped_column(Text)
    category_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    sku_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    processed_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    impact_weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SignalCluster(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "signal_clusters"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    cluster_label: Mapped[str] = mapped_column(Text, nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    centroid_embedding: Mapped[object] = mapped_column(
        Vector(768) if _VECTOR_AVAILABLE else JSONB,
        nullable=False,
    )
    representative_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    cohesion_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
