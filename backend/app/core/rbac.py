"""Centralized RBAC (Role-Based Access Control) for FastAPI endpoints.

Usage:
    from app.core.rbac import require_role

    @router.delete("/{id}")
    async def delete_something(
        _: Annotated[None, require_role(["owner", "admin"])],
        ...
    ):
        ...

``require_role`` already returns a ``Depends(...)`` marker, so use it
directly — do NOT wrap it again in ``Depends(...)``.

Role hierarchy (highest → lowest):
    owner  — full control, including billing and member management
    admin  — management of tenant data, integrations, and settings
    analyst — read-write access to analytics and forecasts
    viewer — read-only access

Endpoints that mutate data or expose sensitive operations must require
at minimum the ``admin`` role. Owner-only operations (billing, member
removal, workspace deletion) must require the ``owner`` role.

Two dependency factories are provided:

* ``require_role(roles)``   — fast path; trusts the JWT claim (token-only).
  Use for read endpoints and non-sensitive mutations.

* ``require_role_db(roles)`` — adds a live DB lookup for callers that would
  be permitted by the token claim, to catch stale roles after a demotion.
  Use for billing mutations, member removal, and workspace-level destructive
  ops where a demoted admin retaining access for up to 1h is unacceptable.
  Adds one DB round-trip per call — do NOT apply to high-frequency paths.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import select

from app.core.exceptions import AuthenticationError, PermissionDeniedError


def require_role(roles: list[str]) -> Any:
    """Return a FastAPI dependency that enforces the user has one of ``roles``.

    Reads the role from ``request.state.role`` (populated from the JWT claim by
    ``TenantContextMiddleware``). Fast — no database round-trip.

    Raises:
        AuthenticationError: if the request has no authenticated user.
        PermissionDeniedError: if the user's role is not in the allowed list.

    Example::

        @router.delete("/{id}")
        async def delete_item(
            _rbac: Annotated[None, require_role(["owner", "admin"])],
            tenant_id: TenantId,
        ):
            ...
    """

    def _check(request: Request) -> None:
        if not getattr(request.state, "tenant_id", None):
            raise AuthenticationError()
        role = getattr(request.state, "role", None)
        if not role or role not in roles:
            allowed = " | ".join(roles)
            raise PermissionDeniedError(
                f"This operation requires role: {allowed}. Your role: {role or 'none'}"
            )

    return Depends(_check)


def require_role_db(roles: list[str]) -> Any:
    """Return a FastAPI dependency that enforces role with a live DB re-check.

    Works identically to ``require_role`` but, for callers whose token claim
    *would* be permitted, additionally queries the database to confirm the
    user's current role has not been changed since the token was issued.

    This closes the window where a demoted admin/owner retains their old role
    for the full ~1h token lifetime. Use on high-sensitivity mutations only
    (billing, member removal, workspace deletion) — it adds one DB round-trip
    per request.

    Raises:
        AuthenticationError: if the request has no authenticated user.
        PermissionDeniedError: if the *current* DB role is not in the allowed
            list (even if the token claim would have passed).
    """

    async def _check_db(request: Request) -> None:
        if not getattr(request.state, "tenant_id", None):
            raise AuthenticationError()

        claim_role = getattr(request.state, "role", None)
        # Fast-reject: if the token claim is already insufficient, deny immediately
        # without touching the database (no benefit in querying further).
        if not claim_role or claim_role not in roles:
            allowed = " | ".join(roles)
            raise PermissionDeniedError(
                f"This operation requires role: {allowed}. Your role: {claim_role or 'none'}"
            )

        # Token claim would be permitted — re-check against the DB to catch
        # demotions that happened after the token was issued.
        user_id: uuid.UUID | None = getattr(request.state, "user_id", None)
        tenant_id: uuid.UUID | None = getattr(request.state, "tenant_id", None)
        if user_id is None or tenant_id is None:
            raise AuthenticationError()

        try:
            from app.models.tenant import User  # avoid circular import at module level

            db = request.app.state.db
            async with db.session(str(tenant_id)) as session:
                db_role_val = await session.scalar(
                    select(User.role).where(
                        User.id == user_id,
                        User.tenant_id == tenant_id,
                        User.is_active.is_(True),
                    )
                )
        except Exception:
            # If the DB is unreachable, fail closed — do not grant access based
            # solely on a potentially-stale token claim for sensitive mutations.
            raise PermissionDeniedError(
                "Unable to verify current role — please retry"
            )

        if db_role_val is None:
            raise AuthenticationError()  # user deactivated / not found

        # db_role_val is an enum instance; get the string value for comparison.
        current_role = db_role_val.value if hasattr(db_role_val, "value") else str(db_role_val)
        if current_role not in roles:
            allowed = " | ".join(roles)
            raise PermissionDeniedError(
                f"This operation requires role: {allowed}. Your current role: {current_role}"
            )

    return Depends(_check_db)


# Pre-built dependencies for the most common restrictions.
# *_db variants add a live DB re-check for sensitive mutations.
require_admin = require_role(["owner", "admin"])
require_owner = require_role(["owner"])

require_admin_db = require_role_db(["owner", "admin"])
require_owner_db = require_role_db(["owner"])
