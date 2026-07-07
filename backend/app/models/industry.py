from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import IndustryCode, SignalType

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class Industry(TimestampMixin, Base):
    __tablename__ = "industries"

    code: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    default_horizon_weeks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    granularity_dimensions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    required_signal_types: Mapped[list[str]] = mapped_column(
        ARRAY(SAEnum(SignalType, name="signal_type")), nullable=False, default=list
    )
    sku_attribute_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    forecast_models: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    optimization_models: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    audit_level: Mapped[str] = mapped_column(Text, nullable=False, default="standard")


class IndustryProfile(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "industry_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        __import__("sqlalchemy.dialects.postgresql", fromlist=["UUID"]).UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    custom_horizon_weeks: Mapped[int | None] = mapped_column(SmallInteger)
    custom_signal_types: Mapped[list[str]] = mapped_column(
        ARRAY(SAEnum(SignalType, name="signal_type")), nullable=False, default=list
    )
    model_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    feature_flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    tenant: Mapped[Tenant] = relationship(
        "Tenant", back_populates="industry_profiles", lazy="raise"
    )
