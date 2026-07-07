from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr

from app.models.enums import IndustryCode, TenantStatus, TenantTier, UserRole


class TenantOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    display_name: str
    tier: TenantTier
    status: TenantStatus
    industries: list[IndustryCode]
    active_industry: IndustryCode
    max_skus: int
    max_users: int
    data_retention_days: int
    settings: dict[str, Any]
    trial_ends_at: datetime | None
    contract_ends_at: datetime | None
    created_at: datetime


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    active_industry: IndustryCode
    is_active: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole = UserRole.analyst
    active_industry: IndustryCode
