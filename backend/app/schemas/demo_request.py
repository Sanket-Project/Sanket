from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DemoRequestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    company: str = Field(min_length=1, max_length=100)
    industry: str = Field(min_length=1, max_length=50)
    tier: str = Field(min_length=1, max_length=50)
    message: str | None = None


class DemoRequestOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    company: str
    industry: str
    tier: str
    message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
