from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Owners can be created only via signup; invites target the manageable roles.
InviteRole = Literal["admin", "analyst", "viewer"]


class InviteCreate(BaseModel):
    email: EmailStr
    role: InviteRole = "viewer"


class InviteOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    role: str
    status: str
    invited_by: uuid.UUID | None
    expires_at: datetime
    created_at: datetime


class InviteCreated(InviteOut):
    """Returned on creation — carries the one-time invite link so the UI can
    surface a copyable URL even when email delivery isn't wired in this env."""

    invite_url: str = Field(description="One-time acceptance link for the invitee")


class InviteList(BaseModel):
    invites: list[InviteOut]
    seats_used: int
    seats_total: int
