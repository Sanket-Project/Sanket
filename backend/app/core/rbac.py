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
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from app.core.exceptions import AuthenticationError, PermissionDeniedError


def require_role(roles: list[str]) -> Any:
    """Return a FastAPI dependency that enforces the user has one of ``roles``.

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


# Pre-built dependencies for the two most common restrictions
require_admin = require_role(["owner", "admin"])
require_owner = require_role(["owner"])
