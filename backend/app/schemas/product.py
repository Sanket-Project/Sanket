from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import IndustryCode, ProductStatus


class ProductCreate(BaseModel):
    external_id: str | None = None
    name: str = Field(min_length=1, max_length=500)
    brand: str | None = None
    category: str = Field(min_length=1, max_length=200)
    subcategory: str | None = None
    status: ProductStatus = ProductStatus.active
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    status: ProductStatus | None = None
    attributes: dict[str, Any] | None = None


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    industry: IndustryCode
    external_id: str | None
    name: str
    brand: str | None
    category: str
    subcategory: str | None
    status: ProductStatus
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SkuCreate(BaseModel):
    external_id: str | None = None
    gtin: str | None = None
    sku_code: str = Field(min_length=1, max_length=200)
    description: str | None = None
    unit_cost: Decimal | None = Field(None, ge=0)
    unit_price: Decimal | None = Field(None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lead_time_days: int | None = Field(None, ge=0)
    moq: int = Field(default=1, ge=1)
    safety_stock: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SkuUpdate(BaseModel):
    description: str | None = None
    unit_cost: Decimal | None = Field(None, ge=0)
    unit_price: Decimal | None = Field(None, ge=0)
    lead_time_days: int | None = Field(None, ge=0)
    moq: int | None = Field(None, ge=1)
    safety_stock: int | None = Field(None, ge=0)
    reorder_point: int | None = Field(None, ge=0)
    attributes: dict[str, Any] | None = None
    is_active: bool | None = None


class SkuOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    industry: IndustryCode
    sku_code: str
    external_id: str | None
    gtin: str | None
    description: str | None
    unit_cost: Decimal | None
    unit_price: Decimal | None
    currency: str
    lead_time_days: int | None
    moq: int
    # Inventory planning params are operator-configured, not part of imported sales
    # data — null means "not yet set" (rendered as "—") rather than a fabricated value.
    safety_stock: int | None
    reorder_point: int | None
    attributes: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
