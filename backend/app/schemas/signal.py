from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import IndustryCode, SignalStatus, SignalType


class ExternalSignalCreate(BaseModel):
    signal_type: SignalType
    source_name: str = Field(min_length=1, max_length=200)
    source_url: str | None = None
    effective_at: datetime
    expires_at: datetime | None = None
    region: str | None = None
    category_tags: list[str] = Field(default_factory=list)
    sku_tags: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    processed_value: Decimal | None = None
    sentiment_score: Decimal | None = Field(None, ge=-1.0, le=1.0)
    impact_weight: Decimal | None = Field(None, ge=0.0, le=1.0)

    @field_validator("expires_at")
    @classmethod
    def expires_after_effective(cls, v: datetime | None, info: Any) -> datetime | None:
        effective = info.data.get("effective_at")
        if v is not None and effective is not None and v <= effective:
            raise ValueError("expires_at must be after effective_at")
        return v


class ExternalSignalOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    industry: IndustryCode
    signal_type: SignalType
    status: SignalStatus
    source_name: str
    source_url: str | None
    effective_at: datetime
    expires_at: datetime | None
    region: str | None
    category_tags: list[str]
    sku_tags: list[str]
    processed_value: Decimal | None
    sentiment_score: Decimal | None
    impact_weight: Decimal | None
    validated_by: uuid.UUID | None
    validated_at: datetime | None
    created_at: datetime
