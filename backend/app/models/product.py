from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import IndustryCode, ProductStatus


class Product(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "products"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, name="product_status"),
        nullable=False,
        default=ProductStatus.active,
    )
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    skus: Mapped[list[Sku]] = relationship("Sku", back_populates="product", lazy="raise")


class Sku(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "skus"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    sku_code: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    lead_time_days: Mapped[int | None] = mapped_column(SmallInteger)
    moq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    safety_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    product: Mapped[Product] = relationship("Product", back_populates="skus", lazy="raise")
    pharma_batches: Mapped[list[PharmaBatch]] = relationship(  # type: ignore[name-defined]
        "PharmaBatch", back_populates="sku", lazy="raise"
    )


from app.models.pharma import PharmaBatch  # noqa: E402

Sku.pharma_batches = relationship("PharmaBatch", back_populates="sku", lazy="raise")  # type: ignore[assignment]
