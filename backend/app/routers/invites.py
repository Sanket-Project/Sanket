"""Team invitation endpoints.

Create / list / revoke pending invites for the active tenant. Used by
onboarding's team step and (later) the members settings panel. Seat usage is
enforced against ``Tenant.max_users`` (active members + outstanding invites).

Email delivery is intentionally not wired here — creation returns a one-time
invite link (relative path; the SPA prepends its origin) so the flow is honest
in every environment rather than fabricating a "sent" state. Acceptance is a
separate authenticated flow (out of scope for this endpoint set).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.rbac import require_admin_db
from app.models.enums import UserRole
from app.models.invite import Invite, InviteStatus
from app.models.tenant import Tenant, User
from app.routers.industry_router import TenantId, UserId
from app.schemas.invite import InviteCreate, InviteCreated, InviteList, InviteOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/invites", tags=["invites"])

INVITE_TTL_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _seats_used(session, tenant_id: uuid.UUID) -> int:
    """Active members + outstanding (pending) invites."""
    active_users = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.is_active.is_(True))
    )
    pending_invites = await session.scalar(
        select(func.count())
        .select_from(Invite)
        .where(Invite.tenant_id == tenant_id, Invite.status == InviteStatus.pending)
    )
    return int(active_users or 0) + int(pending_invites or 0)


@router.get("", response_model=InviteList)
async def list_invites(request: Request, tenant_id: TenantId) -> InviteList:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()
        rows = (
            await session.scalars(
                select(Invite)
                .where(Invite.tenant_id == tenant_id, Invite.status == InviteStatus.pending)
                .order_by(Invite.created_at.desc())
            )
        ).all()
        used = await _seats_used(session, tenant_id)
        return InviteList(
            invites=[InviteOut.model_validate(r) for r in rows],
            seats_used=used,
            seats_total=tenant.max_users,
        )


@router.post("", response_model=InviteCreated, status_code=201)
async def create_invite(
    body: InviteCreate,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: None = require_admin_db,
) -> InviteCreated:
    email = str(body.email).lower()
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise AuthenticationError()

        # Already a member?
        existing_user = await session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == email)
        )
        if existing_user is not None:
            raise ConflictError(f"{email} is already a member of this workspace")

        # Already invited and still pending?
        existing_invite = await session.scalar(
            select(Invite).where(
                Invite.tenant_id == tenant_id,
                Invite.email == email,
                Invite.status == InviteStatus.pending,
            )
        )
        if existing_invite is not None:
            raise ConflictError(f"{email} already has a pending invite")

        if await _seats_used(session, tenant_id) >= tenant.max_users:
            raise ConflictError(
                f"Workspace seat limit reached ({tenant.max_users}). "
                "Revoke a pending invite or upgrade your plan."
            )

        raw_token = secrets.token_urlsafe(32)
        invite = Invite(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=email,
            role=UserRole(body.role),
            status=InviteStatus.pending,
            token_hash=_hash_token(raw_token),
            invited_by=user_id,
            expires_at=datetime.now(tz=UTC) + timedelta(days=INVITE_TTL_DAYS),
        )
        session.add(invite)
        await session.flush()
        out = InviteOut.model_validate(invite)

    log.info("invite.created", tenant_id=str(tenant_id), email=email, role=body.role)
    return InviteCreated(**out.model_dump(), invite_url=f"/accept-invite?token={raw_token}")


@router.delete("/{invite_id}", response_model=InviteOut)
async def revoke_invite(
    invite_id: uuid.UUID,
    request: Request,
    tenant_id: TenantId,
    _rbac: None = require_admin_db,
) -> InviteOut:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        invite = await session.get(Invite, invite_id)
        if invite is None or invite.tenant_id != tenant_id:
            raise NotFoundError("Invite not found")
        invite.status = InviteStatus.revoked
        await session.flush()
        out = InviteOut.model_validate(invite)

    log.info("invite.revoked", tenant_id=str(tenant_id), invite_id=str(invite_id))
    return out
