from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import IndustryCode


class InventoryLevel(UUIDPrimaryKey, TimestampMixin, Base):
    """Current warehouse stock for a SKU at a location.

    One row per (tenant, sku, location) — the *current* position, upserted as
    new stock data arrives (the `as_of` timestamp records when it was last
    measured). This is the real-stock source of truth that the shortage
    detector, replenishment optimizer, and coverage/financial analytics read,
    replacing the previously fabricated `safety_stock * 2` placeholder.

    `available` (on_hand − reserved) is what downstream insight logic should
    treat as sellable stock.
    """

    __tablename__ = "inventory_levels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku_id", "location", name="uq_inventory_tenant_sku_loc"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    location: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    on_hand_units: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    inbound_units: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    reserved_units: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    @property
    def available_units(self) -> Decimal:
        avail = (self.on_hand_units or Decimal("0")) - (self.reserved_units or Decimal("0"))
        return avail if avail > 0 else Decimal("0")
