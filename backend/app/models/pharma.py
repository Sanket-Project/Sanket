from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import GxPBatchStatus


class PharmaBatch(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "pharma_batches"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    lot_number: Mapped[str] = mapped_column(Text, nullable=False)
    ndc_code: Mapped[str | None] = mapped_column(Text)
    manufactured_at: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_produced: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    gxp_status: Mapped[GxPBatchStatus] = mapped_column(
        SAEnum(GxPBatchStatus, name="gxp_batch_status"),
        nullable=False,
        default=GxPBatchStatus.quarantine,
    )
    cold_chain_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_temp_min_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    storage_temp_max_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    qa_released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    qa_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recall_reason: Mapped[str | None] = mapped_column(Text)
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certificate_url: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    sku: Mapped[Sku] = relationship("Sku", back_populates="pharma_batches", lazy="raise")  # type: ignore[name-defined]


from app.models.product import Sku  # noqa: E402
