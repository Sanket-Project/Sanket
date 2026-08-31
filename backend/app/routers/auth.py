"""Authentication endpoints (Firebase-backed).

Flow
----
* **Production / staging (Firebase configured):** the SPA signs in with the
  Firebase JS SDK and obtains an ID token. It then calls ``POST /auth/session``
  with that token to confirm the user is provisioned/active and to fetch its
  tenant context. Every subsequent request carries the Firebase ID token as a
  bearer; ``TenantContextMiddleware`` verifies it.

* **Local dev (Firebase not configured):** ``POST /auth/dev-login`` checks the
  seeded email/password (Argon2) and returns a short-lived HS256 *dev token*
  with the same claim shape as a Firebase ID token. The SPA uses it identically.

The dev path is fenced off in production by ``Settings.require_firebase_in_
production`` and by an explicit ``firebase_enabled`` guard below.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.core.exceptions import (
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    TenantSuspendedError,
    TokenInvalidError,
)
from app.core.firebase_auth import TokenVerificationError, get_verifier
from app.core.login_attempt import (
    IP_MAX_ATTEMPTS,
    MAX_ATTEMPTS,
    _ip_key,
    is_locked_out,
    record_failure,
    record_success,
)
from app.core.security import hash_password, verify_password
from app.middleware.rate_limit import client_ip_from_request
from app.models.enums import TenantStatus
from app.models.invite import Invite, InviteStatus
from app.models.tenant import Tenant, User
from app.schemas.auth import (
    AcceptInviteRequest,
    DevLoginRequest,
    DevLoginResponse,
    FirebaseConfig,
    GoogleSignUpRequest,
    SandboxSessionResponse,
    SessionInfo,
    SignUpRequest,
)
from app.schemas.onboarding import default_onboarding_state, load_onboarding_state
from app.services import audit
from app.services.workspace import create_tenant

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or len(auth) <= 7:
        raise TokenInvalidError()
    return auth[7:]


def _client_ip(request: Request) -> str | None:
    return client_ip_from_request(request, get_settings().trusted_proxy_count)


@router.get("/config", response_model=FirebaseConfig)
async def auth_config(settings: SettingsDep) -> FirebaseConfig:
    """Public, non-secret Firebase web config so the SPA knows which auth mode
    to use. Exposes only values that are safe in a browser bundle."""
    return FirebaseConfig(
        enabled=settings.firebase_enabled,
        project_id=settings.firebase_project_id,
        api_key=settings.firebase_web_api_key,
    )


@router.post("/session", response_model=SessionInfo)
async def session(request: Request, settings: SettingsDep) -> SessionInfo:
    """Exchange a verified bearer token for the user's tenant context.

    Verifies the token (Firebase ID token or dev token), confirms the user is
    provisioned + active and the tenant is not suspended, lazily backfills the
    Firebase UID / custom claims on first sign-in, and returns session metadata.
    """
    token = _bearer(request)
    try:
        identity = await run_in_threadpool(get_verifier().verify_identity, token)
    except TokenVerificationError as exc:
        log.info("auth.session.verify_failed", error=str(exc))
        raise TokenInvalidError() from exc

    uid = str(identity.get("uid") or identity.get("sub") or "")
    email = identity.get("email")
    puid = identity.get("puid")
    if not uid:
        raise TokenInvalidError()

    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        # Resolve the user: Firebase UID first, then SANKET id (dev token), then
        # email (first-login backfill before the UID is linked).
        user_row: User | None = None
        if uid:
            user_row = await db_session.scalar(select(User).where(User.firebase_uid == uid))
        if user_row is None and puid:
            try:
                user_row = await db_session.get(User, uuid.UUID(str(puid)))
            except (ValueError, TypeError):
                user_row = None
        if user_row is None and email:
            user_row = await db_session.scalar(select(User).where(User.email == email))

        if user_row is None and email and not settings.is_production:
            tenant_row = await db_session.scalar(select(Tenant).where(Tenant.slug == "sanket-dev"))
            if tenant_row is not None:
                from app.models.enums import UserRole

                candidate = User(
                    id=uuid.uuid4(),
                    tenant_id=tenant_row.id,
                    email=email,
                    firebase_uid=uid,
                    full_name=identity.get("name") or email.split("@")[0].capitalize(),
                    role=UserRole.admin,
                    is_active=True,
                )
                # Insert inside a savepoint so a concurrent first-login (which races
                # on uq_users_tenant_email) doesn't poison the outer transaction. On
                # conflict we roll back the savepoint and re-fetch the row the other
                # request just created.
                try:
                    async with db_session.begin_nested():
                        db_session.add(candidate)
                        await db_session.flush()
                    user_row = candidate
                    log.info(
                        "auth.session.auto_provision",
                        email=email,
                        uid=uid,
                        tenant_slug="sanket-dev",
                    )
                except IntegrityError:
                    user_row = await db_session.scalar(
                        select(User).where(User.tenant_id == tenant_row.id, User.email == email)
                    )
                    log.info("auth.session.auto_provision_raced", email=email, uid=uid)

        if user_row is None:
            # When Firebase is enabled (production) a missing user means this is
            # a first-time Google sign-in with no SANKET account yet.  Return a
            # structured 404 so the frontend can show the workspace-setup modal
            # rather than a generic "Invalid credentials" error.
            if settings.firebase_enabled:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="google_account_not_provisioned",
                )
            raise InvalidCredentialsError()

        if not user_row.is_active:
            raise InvalidCredentialsError()

        tenant_row = await db_session.get(Tenant, user_row.tenant_id)
        if tenant_row is None:
            raise InvalidCredentialsError()
        if tenant_row.status == TenantStatus.suspended:
            raise TenantSuspendedError()

        # First-login linking + claim sync (Firebase mode only).
        if settings.firebase_enabled:
            if user_row.firebase_uid != uid:
                await db_session.execute(
                    update(User).where(User.id == user_row.id).values(firebase_uid=uid)
                )
            # The workspace is authoritative for `ind`. Comparing against the
            # user row instead would let a stale member value -- one written
            # before the inheritance trigger existed -- reissue a claim for an
            # industry the workspace is not scoped to.
            claims_stale = (
                str(identity.get("puid")) != str(user_row.id)
                or str(identity.get("tid")) != str(user_row.tenant_id)
                or str(identity.get("role")) != user_row.role.value
                or str(identity.get("ind")) != tenant_row.industry.value
            )
            if claims_stale:
                await run_in_threadpool(
                    get_verifier().set_user_claims,
                    uid,
                    puid=str(user_row.id),
                    tid=str(user_row.tenant_id),
                    role=user_row.role.value,
                    ind=tenant_row.industry.value,
                )

        await db_session.execute(
            update(User).where(User.id == user_row.id).values(last_login_at=datetime.now(tz=UTC))
        )
        await audit.record(
            db_session,
            tenant_id=tenant_row.id,
            user_id=user_row.id,
            action="user.login",
            entity_type="user",
            entity_id=str(user_row.id),
            industry=tenant_row.industry,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )

        result = SessionInfo(
            user_id=user_row.id,
            tenant_id=tenant_row.id,
            role=user_row.role.value,
            active_industry=tenant_row.industry.value,
            email=user_row.email,
            full_name=user_row.full_name,
            onboarding=load_onboarding_state(tenant_row.settings),
        )

    log.info("auth.session.ok", user_id=str(result.user_id), tenant_id=str(result.tenant_id))
    return result


@router.post("/dev-login", response_model=DevLoginResponse)
async def dev_login(
    body: DevLoginRequest, request: Request, settings: SettingsDep
) -> DevLoginResponse:
    """Local dev-only login. Returns a short-lived dev identity token.

    Disabled whenever Firebase is configured (and therefore always disabled in
    production, which requires Firebase)."""
    if settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    redis_client = getattr(request.app.state, "redis", None)
    attempt_key = _ip_key(body.tenant_slug, body.email)
    # Brute-force gate keyed on (tenant, email) AND client IP. The IP gate uses a
    # higher threshold to tolerate shared NAT while still catching attackers who
    # rotate the email to dodge the per-account counter.
    ip = _client_ip(request) or "unknown"
    ip_key = f"login_attempt:ip:{ip}"
    for key, limit in ((attempt_key, MAX_ATTEMPTS), (ip_key, IP_MAX_ATTEMPTS)):
        locked, retry_after = await is_locked_out(key, redis_client, max_attempts=limit)
        if locked:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        tenant_row = await db_session.scalar(select(Tenant).where(Tenant.slug == body.tenant_slug))
        if tenant_row is None:
            await record_failure(attempt_key, redis_client)
            await record_failure(ip_key, redis_client)
            raise InvalidCredentialsError()
        if tenant_row.status == TenantStatus.suspended:
            raise TenantSuspendedError()

        user_row = await db_session.scalar(
            select(User).where(
                User.tenant_id == tenant_row.id,
                User.email == body.email,
                User.is_active.is_(True),
            )
        )
        if (
            user_row is None
            or not user_row.password_hash
            or not verify_password(body.password, user_row.password_hash, settings)
        ):
            await record_failure(attempt_key, redis_client)
            await record_failure(ip_key, redis_client)
            raise InvalidCredentialsError()

        await record_success(attempt_key, redis_client)
        await record_success(ip_key, redis_client)
        await db_session.execute(
            update(User).where(User.id == user_row.id).values(last_login_at=datetime.now(tz=UTC))
        )
        await audit.record(
            db_session,
            tenant_id=tenant_row.id,
            user_id=user_row.id,
            action="user.login",
            entity_type="user",
            entity_id=str(user_row.id),
            industry=tenant_row.industry,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )

        token, expires_in = get_verifier().mint_dev_token(
            uid=str(user_row.id),
            puid=str(user_row.id),
            email=user_row.email,
            tid=str(tenant_row.id),
            role=user_row.role.value,
            ind=tenant_row.industry.value,
        )
        response = DevLoginResponse(
            access_token=token,
            expires_in=expires_in,
            user_id=user_row.id,
            tenant_id=tenant_row.id,
            role=user_row.role.value,
            active_industry=tenant_row.industry.value,
            email=user_row.email,
            full_name=user_row.full_name,
            onboarding=load_onboarding_state(tenant_row.settings),
        )

    log.info("auth.dev_login.ok", user_id=str(response.user_id))
    return response


@router.post("/sandbox-session", response_model=SandboxSessionResponse)
async def sandbox_session(request: Request, settings: SettingsDep) -> SandboxSessionResponse:
    """Start a session for the shared public demo account — server-side.

    The marketing site's "Try the Sandbox" button calls this with no body. The
    backend looks up the configured demo tenant/user and mints a token for it
    (a dev token in dev mode, a Firebase custom token in Firebase mode). No
    password is ever sent to or from the browser, so nothing secret ships in the
    client bundle.
    """
    if not settings.sandbox_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        tenant_row = await db_session.scalar(
            select(Tenant).where(Tenant.slug == settings.sandbox_tenant_slug)
        )
        if tenant_row is None:
            log.warning("auth.sandbox.tenant_missing", slug=settings.sandbox_tenant_slug)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sandbox is temporarily unavailable",
            )
        if tenant_row.status == TenantStatus.suspended:
            raise TenantSuspendedError()

        user_row = await db_session.scalar(
            select(User).where(
                User.tenant_id == tenant_row.id,
                User.email == settings.sandbox_email,
                User.is_active.is_(True),
            )
        )
        if user_row is None:
            log.warning("auth.sandbox.user_missing", email=settings.sandbox_email)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sandbox is temporarily unavailable",
            )

        verifier = get_verifier()
        custom_token: str | None = None
        access_token: str | None = None
        expires_in: int | None = None

        if settings.firebase_enabled:
            # Resolve (or lazily create, passwordless) the demo Firebase user,
            # stamp its claims so the exchanged ID token carries tenant context,
            # then hand the SPA a custom token to sign in with.
            uid = await run_in_threadpool(verifier.get_uid_by_email, settings.sandbox_email)
            if uid is None:
                uid = await run_in_threadpool(
                    verifier.create_or_get_user,
                    email=settings.sandbox_email,
                    password=None,
                    display_name=user_row.full_name,
                )
            if user_row.firebase_uid != uid:
                await db_session.execute(
                    update(User).where(User.id == user_row.id).values(firebase_uid=uid)
                )
            claims = {
                "puid": str(user_row.id),
                "tid": str(tenant_row.id),
                "role": user_row.role.value,
                "ind": tenant_row.industry.value,
            }
            custom_token = await run_in_threadpool(verifier.create_custom_token, uid, claims)
            mode = "firebase"
        else:
            access_token, expires_in = verifier.mint_dev_token(
                uid=str(user_row.id),
                puid=str(user_row.id),
                email=user_row.email,
                tid=str(tenant_row.id),
                role=user_row.role.value,
                ind=tenant_row.industry.value,
            )
            mode = "dev"

        await db_session.execute(
            update(User).where(User.id == user_row.id).values(last_login_at=datetime.now(tz=UTC))
        )
        await audit.record(
            db_session,
            tenant_id=tenant_row.id,
            user_id=user_row.id,
            action="user.sandbox_login",
            entity_type="user",
            entity_id=str(user_row.id),
            industry=tenant_row.industry,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )

        response = SandboxSessionResponse(
            mode=mode,
            access_token=access_token,
            custom_token=custom_token,
            expires_in=expires_in,
            user_id=user_row.id,
            tenant_id=tenant_row.id,
            role=user_row.role.value,
            active_industry=tenant_row.industry.value,
            email=user_row.email,
            full_name=user_row.full_name,
            onboarding=load_onboarding_state(tenant_row.settings),
        )

    log.info("auth.sandbox.ok", mode=mode, user_id=str(response.user_id))
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, settings: SettingsDep) -> None:
    """Revoke the caller's Firebase refresh tokens (real mode) and audit.

    Relies on ``TenantContextMiddleware`` having already verified the bearer and
    populated ``request.state``."""
    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    firebase_uid = getattr(request.state, "firebase_uid", None)
    if user_id is None or tenant_id is None:
        return

    if settings.firebase_enabled and firebase_uid:
        try:
            await run_in_threadpool(get_verifier().revoke_refresh_tokens, firebase_uid)
        except Exception as exc:  # never fail logout on a revoke hiccup
            log.warning("auth.logout.revoke_failed", error=str(exc))

    db = request.app.state.db
    async with db.session(str(tenant_id)) as db_session:
        await audit.record(
            db_session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="user.logout",
            entity_type="user",
            entity_id=str(user_id),
            request_id=getattr(request.state, "request_id", None),
        )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignUpRequest, request: Request, settings: SettingsDep) -> dict:
    """Create a new tenant and user.

    If Firebase is enabled, also registers the user in Firebase Auth and sets custom claims.
    """
    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        # Check if user email already exists
        existing_user = await db_session.scalar(select(User).where(User.email == body.email))
        if existing_user is not None:
            raise ConflictError(f"Email '{body.email}' is already registered")

        # Create a NEW tenant only. Self-service signup must never let a caller
        # join an EXISTING tenant by guessing its slug — that would be broken
        # access control (unauthorized entry into another customer's workspace).
        # Adding users to an existing tenant goes through an authenticated,
        # owner/admin-driven invite flow, not this public endpoint.
        existing_tenant = await db_session.scalar(
            select(Tenant).where(Tenant.slug == body.tenant_slug)
        )
        if existing_tenant is not None:
            raise ConflictError(f"Workspace '{body.tenant_slug}' is not available")

        tenant_row = await create_tenant(
            db_session,
            slug=body.tenant_slug,
            display_name=body.tenant_slug.capitalize(),
            industry=body.industry,
        )

        from app.models.enums import UserRole

        # First user of every new tenant is the owner.
        # (Joining an existing tenant via invite is a separate, authenticated flow.)
        role = UserRole.owner

        # No industry on the user: members inherit the workspace's, enforced by
        # the trg_users_inherit_industry trigger.
        user_row = User(
            id=uuid.uuid4(),
            tenant_id=tenant_row.id,
            email=body.email,
            password_hash=hash_password(body.password, settings),
            full_name=body.name,
            role=role,
            is_active=True,
        )
        db_session.add(user_row)
        await db_session.flush()

        # Firebase provisioning if enabled
        firebase_uid = None
        if settings.firebase_enabled:
            try:
                firebase_uid = await run_in_threadpool(
                    get_verifier().create_or_get_user,
                    email=body.email,
                    password=body.password,
                    display_name=body.name,
                    reset_password=True,
                )
                user_row.firebase_uid = firebase_uid
                await db_session.flush()

                # Sync claims immediately, from the workspace's industry.
                await run_in_threadpool(
                    get_verifier().set_user_claims,
                    firebase_uid,
                    puid=str(user_row.id),
                    tid=str(tenant_row.id),
                    role=role.value,
                    ind=tenant_row.industry.value,
                )
            except Exception as exc:
                log.error("auth.signup.firebase_provision_failed", error=str(exc))
                # Roll back DB changes if Firebase fails to keep state consistent.
                # Do not echo the upstream error verbatim (info disclosure).
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Account provisioning failed. Please try again.",
                ) from exc

        await db_session.commit()

    log.info(
        "auth.signup.ok",
        email=body.email,
        tenant_slug=body.tenant_slug,
        firebase_uid=firebase_uid,
    )
    return {"status": "ok", "user_id": str(user_row.id), "tenant_id": str(tenant_row.id)}


@router.post("/google-signup", response_model=SessionInfo, status_code=status.HTTP_201_CREATED)
async def google_signup(
    body: GoogleSignUpRequest, request: Request, settings: SettingsDep
) -> SessionInfo:
    """Provision a new SANKET tenant + user for a first-time Google sign-in.

    Verifies the Firebase ID token, creates the Tenant + User (no password),
    links the firebase_uid, sets custom claims, and returns SessionInfo so the
    SPA can complete the login without a second round-trip.

    Only available when Firebase is enabled (i.e. never in dev-fallback mode).
    """
    if not settings.firebase_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    # Verify the Firebase token — this gives us the canonical uid + email.
    try:
        identity = await run_in_threadpool(get_verifier().verify_identity, body.id_token)
    except TokenVerificationError as exc:
        log.info("auth.google_signup.verify_failed", error=str(exc))
        raise TokenInvalidError() from exc

    uid = str(identity.get("uid") or identity.get("sub") or "")
    email = identity.get("email")
    if not uid or not email:
        raise TokenInvalidError()

    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        # Guard: email already registered (e.g. user signed up with password before).
        existing_user = await db_session.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            raise ConflictError(f"An account for '{email}' already exists. Please sign in instead.")

        # Guard: workspace slug already taken.
        existing_tenant = await db_session.scalar(
            select(Tenant).where(Tenant.slug == body.workspace_slug)
        )
        if existing_tenant is not None:
            raise ConflictError(f"Workspace '{body.workspace_slug}' is not available")

        from app.models.enums import UserRole

        # Identical to the password path, deliberately: one create_tenant call,
        # so the Google flow cannot drift back into granting every vertical.
        tenant_row = await create_tenant(
            db_session,
            slug=body.workspace_slug,
            display_name=body.workspace_slug.replace("-", " ").title(),
            industry=body.industry,
        )

        user_row = User(
            id=uuid.uuid4(),
            tenant_id=tenant_row.id,
            email=email,
            firebase_uid=uid,
            full_name=body.name or (email.split("@")[0].replace(".", " ").title()),
            role=UserRole.owner,
            is_active=True,
        )
        db_session.add(user_row)
        await db_session.flush()

        # Set custom claims so future ID tokens carry tenant context.
        try:
            await run_in_threadpool(
                get_verifier().set_user_claims,
                uid,
                puid=str(user_row.id),
                tid=str(tenant_row.id),
                role=UserRole.owner.value,
                ind=tenant_row.industry.value,
            )
        except Exception as exc:
            log.error("auth.google_signup.claims_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Account provisioning failed — please try again.",
            ) from exc

        await db_session.execute(
            update(User).where(User.id == user_row.id).values(last_login_at=datetime.now(tz=UTC))
        )
        await audit.record(
            db_session,
            tenant_id=tenant_row.id,
            user_id=user_row.id,
            action="user.google_signup",
            entity_type="user",
            entity_id=str(user_row.id),
            industry=tenant_row.industry,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )
        await db_session.commit()

    log.info(
        "auth.google_signup.ok",
        email=email,
        workspace_slug=body.workspace_slug,
        uid=uid,
    )
    return SessionInfo(
        user_id=user_row.id,
        tenant_id=tenant_row.id,
        role=UserRole.owner.value,
        active_industry=tenant_row.industry.value,
        email=user_row.email,
        full_name=user_row.full_name,
        # Freshly provisioned tenant — seeded in_progress above. Built from the
        # default rather than re-reading the (now committed/expired) row.
        onboarding=default_onboarding_state(),
    )


@router.post("/accept-invite", response_model=SessionInfo, status_code=201)
async def accept_invite(
    body: AcceptInviteRequest, request: Request, settings: SettingsDep
) -> SessionInfo:
    """Redeem an invitation and join its workspace.

    Public, because the invitee has no bearer yet -- ``routers/invites.py`` has
    always minted a link to ``/accept-invite?token=...`` and nothing has ever
    redeemed it.

    Everything that decides privilege is read from the invite row: which
    workspace, which role, and (via the workspace) which industry. The request
    supplies only the invitee's own name and password. Extra fields in the body
    are ignored, so an attacker cannot promote themselves by adding ``role``.

    The token is compared by SHA-256 hash, matching how ``POST /invites`` stored
    it. A single-use check, an expiry check and a seat re-check all run here
    rather than only at invite time, because all three can change in the days
    between sending a link and someone clicking it.
    """
    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()

    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        invite = await db_session.scalar(
            select(Invite).where(
                Invite.token_hash == token_hash,
                Invite.status == InviteStatus.pending,
            )
        )
        # One shape of failure for unknown, already-used, revoked and expired
        # links: distinguishing them would let someone probe which invitations
        # exist for an address they do not control.
        if invite is None or invite.expires_at <= datetime.now(tz=UTC):
            raise NotFoundError("Invite")

        tenant_row = await db_session.get(Tenant, invite.tenant_id)
        if tenant_row is None or tenant_row.status == TenantStatus.suspended:
            raise NotFoundError("Invite")

        existing = await db_session.scalar(
            select(User).where(
                User.tenant_id == invite.tenant_id, User.email == invite.email
            )
        )
        if existing is not None:
            raise ConflictError("That invitation has already been used")

        seats_used = await db_session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == invite.tenant_id, User.is_active.is_(True))
        )
        if int(seats_used or 0) >= tenant_row.max_users:
            raise ConflictError(
                "This workspace has no seats available. Ask an admin to free one "
                "or upgrade the plan."
            )

        # No industry passed: trg_users_inherit_industry stamps the workspace's.
        user_row = User(
            id=uuid.uuid4(),
            tenant_id=invite.tenant_id,
            email=invite.email,
            password_hash=hash_password(body.password, settings),
            full_name=body.name,
            role=invite.role,
            is_active=True,
        )
        db_session.add(user_row)
        invite.status = InviteStatus.accepted
        await db_session.flush()

        if settings.firebase_enabled:
            try:
                firebase_uid = await run_in_threadpool(
                    get_verifier().create_or_get_user,
                    email=invite.email,
                    password=body.password,
                    display_name=body.name,
                    reset_password=True,
                )
                user_row.firebase_uid = firebase_uid
                await db_session.flush()
                await run_in_threadpool(
                    get_verifier().set_user_claims,
                    firebase_uid,
                    puid=str(user_row.id),
                    tid=str(tenant_row.id),
                    role=invite.role.value,
                    ind=tenant_row.industry.value,
                )
            except Exception as exc:
                log.error("auth.accept_invite.firebase_failed", error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Account provisioning failed. Please try again.",
                ) from exc

        await audit.record(
            db_session,
            tenant_id=tenant_row.id,
            user_id=user_row.id,
            action="user.invite_accepted",
            entity_type="user",
            entity_id=str(user_row.id),
            industry=tenant_row.industry,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )

        result = SessionInfo(
            user_id=user_row.id,
            tenant_id=tenant_row.id,
            role=invite.role.value,
            active_industry=tenant_row.industry.value,
            email=user_row.email,
            full_name=user_row.full_name,
            onboarding=load_onboarding_state(tenant_row.settings),
        )
        await db_session.commit()

    log.info(
        "auth.accept_invite.ok",
        tenant_id=str(result.tenant_id),
        role=result.role,
    )
    return result
