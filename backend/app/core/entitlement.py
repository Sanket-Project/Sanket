"""Server-side subscription entitlement.

Until this existed, the paywall was `SubscriptionGate.tsx` — a React component
with nothing behind it. A tenant with no subscription row at all got 200 from
`/products`, `/skus`, `/inventory/levels`, `/signals`, `/alerts`,
`/webhooks/endpoints`, `/financial/impact` and `/billing/usage`
(docs/audit/02 P0-1). Anyone who opened devtools used the product for free, and
cancelling changed nothing because nothing was ever enforced.

Authority: the ``subscriptions`` table, never ``tenants.tier``
------------------------------------------------------------
Both exist and nothing reconciles them. ``subscriptions`` wins, because
``tenants.tier`` is written and never read:

* every tenant-creation path hardcodes ``TenantTier.growth`` — the seed
  (``core/database.py:281``) and both signup paths
  (``routers/auth.py:517``, ``:688``);
* no subscription transition updates it — ``SubscriptionManager`` never
  touches the ``Tenant`` row;
* observed in this database: 10 of 11 tenants sit at ``tier='growth'`` /
  ``status='trial'``, including six with **no subscription row at all**.

So gating on ``tenants.tier`` would hand Growth-tier entitlement to every
tenant that never paid — precisely the bug being fixed. ``subscriptions``
carries the only state that actually moves: ``status`` and
``current_period_end``.

Reconciliation the other side still needs (not done here, see docs/audit/05):
``tenants.tier`` and ``tenants.status`` should either be dropped, or maintained
as a denormalised read-model updated by ``SubscriptionManager`` on every status
transition and derived from the live subscription's ``plans.tier``. Until then
nothing may read them for an access decision.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import Depends, Request
from sqlalchemy import select

from app.core.exceptions import AuthenticationError, SubscriptionRequiredError
from app.models.billing import Subscription, SubscriptionStatus

log = structlog.get_logger(__name__)

# The only two statuses that grant access. Deliberately narrower than
# `LIVE_STATUSES` in subscription_manager: `past_due` occupies the tenant's
# single live-subscription slot (so it must block a second subscription) but
# must NOT grant access — a failed payment is exactly when access should stop.
ENTITLED_STATUSES: tuple[SubscriptionStatus, ...] = (
    SubscriptionStatus.trialing,
    SubscriptionStatus.active,
)

# Paths on an otherwise-gated router that a tenant must reach before they have
# paid for anything. The onboarding wizard runs outside AppShell — and therefore
# outside the paywall — so its data step posts a CSV/Excel file before the
# tenant has ever seen a plan. Gating these would deadlock the funnel.
#
# The boundary is "you can put data in, you cannot get anything out": these two
# accept an upload, and every endpoint that reads products, SKUs, forecasts,
# signals or analytics back out stays gated. An unsubscribed tenant can finish
# setup and import a catalogue, and see none of it.
#
# Kept here rather than as per-route `dependencies=` so the complete list of
# ungated tenant-data paths is auditable in one place.
_SETUP_PATHS: frozenset[str] = frozenset(
    [
        "/api/v1/integrations/upload",
        "/api/v1/integrations/upload/analyze",
    ]
)


def require_active_subscription() -> Any:
    """FastAPI dependency: allow only tenants holding a live subscription.

    Entitled means ``status in (active, trialing)`` **and**
    ``current_period_end > now()``. Both halves matter: a row left at
    ``active`` with an elapsed period is exactly what a missed cancellation
    webhook produces, and status alone would keep that workspace open forever.

    Returns ``Depends(...)`` already applied — use it directly:

        app.include_router(products_router, dependencies=[require_active_subscription()])
    """

    async def _check(request: Request) -> None:
        # Endpoints the auth middleware treats as public authenticate
        # themselves (Shopify HMAC, Razorpay HMAC, the push-ingest token) and
        # have no JWT tenant context. Delegating to the middleware's own
        # predicate keeps the two lists from drifting apart.
        from app.middleware.tenant_context import TenantContextMiddleware

        if TenantContextMiddleware._is_public(request):
            return

        if request.url.path in _SETUP_PATHS:
            return

        tenant_id: uuid.UUID | None = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            # Non-public path with no tenant context: the middleware should
            # already have rejected this. Fail closed rather than assume.
            raise AuthenticationError()

        try:
            db = request.app.state.db
            async with db.session(str(tenant_id)) as session:
                sub = await session.scalar(
                    select(Subscription)
                    .where(
                        Subscription.tenant_id == tenant_id,
                        Subscription.status.in_(ENTITLED_STATUSES),
                    )
                    .order_by(Subscription.current_period_end.desc())
                    .limit(1)
                )
        except Exception as exc:
            # Fail closed, matching require_role_db. An unreachable database
            # must not silently become "everyone is entitled" — that is the
            # failure mode this module exists to remove.
            log.error(
                "entitlement.check_failed",
                tenant=str(tenant_id),
                path=request.url.path,
                error=str(exc),
            )
            raise SubscriptionRequiredError(
                "Unable to verify your subscription — please retry."
            ) from exc

        if sub is None:
            log.info(
                "entitlement.denied",
                tenant=str(tenant_id),
                path=request.url.path,
                reason="no_live_subscription",
            )
            raise SubscriptionRequiredError()

        if sub.current_period_end <= datetime.now(tz=UTC):
            log.info(
                "entitlement.denied",
                tenant=str(tenant_id),
                path=request.url.path,
                reason="period_elapsed",
                status=sub.status.value,
                period_end=sub.current_period_end.isoformat(),
            )
            raise SubscriptionRequiredError(
                "Your subscription period has ended. Renew to continue."
            )

    return Depends(_check)
