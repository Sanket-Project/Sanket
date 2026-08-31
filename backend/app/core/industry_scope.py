"""The industry authorization boundary.

Distinct from tenant isolation, and deliberately kept that way. RLS answers
*whose company data may this user read*; this module answers *which product
modules may this company access*. Conflating them is how the previous model
went wrong -- industry access was policed by a token claim that signup filled
with all five verticals, while RLS quietly did the only real work.

Before this existed the boundary was not enforced at all. Every router under
``routers/industries/`` took an ``ActiveIndustry`` dependency and then hardcoded
its own ``IndustryCode`` in each query without ever comparing the two, so a
fashion tenant got a 200 from ``/pharma/overview``. RLS still scoped the rows to
their own tenant, so nothing leaked between customers -- but the industry
boundary was decorative.

``require_industry`` is applied at ``include_router`` registration rather than
per-endpoint, mirroring the subscription paywall in ``main.py``: a new endpoint
inherits the gate by construction, because its author never writes it.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.enums import IndustryCode


def tenant_industry(request: Request) -> IndustryCode:
    """The calling workspace's one authoritative industry.

    Read from the verified token claim that ``TenantContextMiddleware`` puts on
    the request. The claim is minted from ``tenants.industry`` at every
    provisioning path, and once a workspace locks nothing can change it -- so it
    cannot drift. The single path that *can* change it (correction during setup)
    revokes the user's refresh tokens, so a superseded value cannot be replayed.

    Lock state is a different question and is never answered from a claim: see
    ``routers/industry_router._industry_is_locked``, which reads the database.
    """
    if getattr(request.state, "tenant_id", None) is None:
        raise AuthenticationError()
    code = getattr(request.state, "industry_code", None)
    if code is None:
        raise AuthenticationError("Industry context missing from token")
    try:
        return IndustryCode(code)
    except ValueError:
        raise AuthenticationError("Industry context missing from token") from None


TenantIndustry = Annotated[IndustryCode, Depends(tenant_industry)]


def require_industry(code: IndustryCode) -> Any:
    """Dependency: this router serves only workspaces scoped to ``code``.

    Already returns ``Depends(...)`` -- pass it straight into
    ``include_router(dependencies=...)``; do NOT wrap it again.
    """

    def _check(request: Request) -> None:
        if tenant_industry(request) is not code:
            raise PermissionDeniedError(
                f"This workspace is not configured for the {code.value} industry"
            )

    return Depends(_check)


def assert_industry(
    requested: str | IndustryCode | None, tenant: IndustryCode
) -> IndustryCode:
    """Resolve a client-supplied industry against the workspace's own.

    ``None`` means "the workspace's" -- the only correct default now that a
    client may not choose. Any other value must match, or it is a 403 rather
    than a silent coercion: an old client posting a mismatched
    ``target_industry`` is telling us it believes it can write somewhere it
    cannot, and that deserves an error, not a quiet redirect.
    """
    if requested is None:
        return tenant
    try:
        value = IndustryCode(requested)
    except ValueError:
        raise ValidationError(f"Unknown industry code: {requested}") from None
    if value is not tenant:
        raise PermissionDeniedError(
            f"This workspace is not configured for the {value.value} industry"
        )
    return tenant
