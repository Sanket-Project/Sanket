"""Persisted decisions — the ledger the ROI dashboard is computed from.

A recommendation is stored the moment it is shown, not when it is accepted, and
it carries a frozen copy of every input it was derived from (``inputs``) plus
the spreadsheet baseline it is being compared against (``baseline_units``).

That matters because the ROI screen makes a financial claim to a CEO. "We
released ₹75 lakh of working capital" is only defensible if each rupee traces
back to a specific SKU, on a specific date, where the user accepted an order of
N units instead of the baseline's M — with the forecast, lead time, and service
level that produced both still attached. Recomputing after the fact from
today's data would silently rewrite history every time a lead time changed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import (
    DecisionKind,
    DecisionStatus,
    DecisionUrgency,
    IndustryCode,
)


class Recommendation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_tenant_status", "tenant_id", "status"),
        Index("ix_recommendations_tenant_sku", "tenant_id", "sku_id"),
        Index("ix_recommendations_decided_at", "tenant_id", "decided_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL")
    )
    source_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL")
    )

    kind: Mapped[DecisionKind] = mapped_column(
        SAEnum(DecisionKind, name="decision_kind", create_constraint=False, native_enum=False),
        nullable=False,
    )
    status: Mapped[DecisionStatus] = mapped_column(
        SAEnum(DecisionStatus, name="decision_status", create_constraint=False, native_enum=False),
        nullable=False,
        default=DecisionStatus.open,
    )
    urgency: Mapped[DecisionUrgency] = mapped_column(
        SAEnum(DecisionUrgency, name="decision_urgency", create_constraint=False, native_enum=False),
        nullable=False,
        default=DecisionUrgency.normal,
    )

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: What a p90-cover spreadsheet policy would have ordered. The delta against
    #: ``recommended_units`` is the working-capital claim on the ROI screen.
    baseline_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: What the user actually committed to, if they edited the quantity.
    accepted_units: Mapped[int | None] = mapped_column(Integer)

    confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    confidence_band: Mapped[str] = mapped_column(Text, nullable=False, default="insufficient")

    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")

    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    economics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Set when a shortage alert for the same SKU was open at generation time —
    #: this is what lets the ROI ledger count "stockouts avoided" honestly.
    linked_alert_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    dismissal_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
