"""Multi-region request router.

If a tenant's `home_region` doesn't match this cell's deploy region, we return
a 421 Misdirected Request with the canonical URL so the client (or a smart
edge proxy) can redirect to the right cell. The intent is sticky residency:
EU tenant data never enters US-region clusters.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings

log = structlog.get_logger(__name__)

# Free paths must work cross-region (e.g. /api/v1/auth/login routes to the
# tenant's home region after the slug lookup)
_REGION_FREE_PATHS = (
    "/health",
    "/metrics",
    "/",
    "/ws",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/billing/razorpay/webhook",
)


class RegionRouterMiddleware(BaseHTTPMiddleware):
    """Reject (or redirect) requests routed to the wrong region cell."""

    def __init__(self, app, *, deploy_region: str | None = None) -> None:
        super().__init__(app)
        settings = get_settings()
        self._deploy_region = deploy_region or getattr(settings, "deploy_region", None) or "us-east"
        self._cache: dict[uuid.UUID, str] = {}  # tenant_id → home_region

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _REGION_FREE_PATHS or any(
            request.url.path.startswith(p) for p in ("/static/", "/docs", "/openapi.json", "/redoc")
        ):
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None:
            return await call_next(request)

        home = self._cache.get(tenant_id)
        if home is None:
            db = request.app.state.db
            try:
                async with db.session_no_rls() as session:
                    res = await session.execute(
                        text("SELECT home_region::text FROM tenants WHERE id = :tid"),
                        {"tid": str(tenant_id)},
                    )
                    row = res.first()
                    if row:
                        home = row[0]
                        self._cache[tenant_id] = home
            except Exception as exc:
                log.warning("region.lookup_failed", error=str(exc))
                return await call_next(request)

        if home and home != self._deploy_region:
            target_host = f"https://{home}.sanket.example"
            return JSONResponse(
                status_code=421,
                content={
                    "detail": "Misdirected request — tenant lives in another region",
                    "tenant_home_region": home,
                    "redirect_to": f"{target_host}{request.url.path}",
                },
                headers={"Location": f"{target_host}{request.url.path}"},
            )
        return await call_next(request)
