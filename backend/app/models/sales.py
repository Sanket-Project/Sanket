from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import IndustryCode


class HistoricalSale(Base):
    """Partitioned by sale_time (RANGE). Do not add FKs — partitioned tables
    do not support FK constraints in PostgreSQL without partition-aware DDL."""

    __tablename__ = "historical_sales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    sale_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    region: Mapped[str | None] = mapped_column(Text)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    net_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    returns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    markdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __mapper_args__ = {"primary_key": [id, sale_time]}
