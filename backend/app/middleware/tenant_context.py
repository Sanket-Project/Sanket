from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.core.firebase_auth import TokenVerificationError, get_verifier
from app.models.enums import IndustryCode

log = structlog.get_logger(__name__)

_PUBLIC_PATHS: frozenset[str] = frozenset(
    [
        "/",
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/config",
        "/api/v1/auth/session",
        "/api/v1/auth/dev-login",
        # Self-service registration: a brand-new user has no bearer yet.
        "/api/v1/auth/signup",
        # Google OAuth first-time sign-in: the Firebase ID token is in the
        # request body (verified server-side); no bearer header exists yet.
        "/api/v1/auth/google-signup",
        # Public demo: authenticates the shared sandbox account server-side, so
        # it must be reachable without an existing bearer.
        "/api/v1/auth/sandbox-session",
        # Shopify calls this server-to-server with its own HMAC signature (no
        # bearer); the handler verifies authenticity itself.
        "/api/v1/integrations/shopify/webhook",
        # Generic push ingest (rest_api / webhooks connectors): authenticated by
        # the per-connection push token (X-Sanket-Token / Bearer), not a JWT —
        # the handler resolves the tenant from the token hash itself.
        "/api/v1/integrations/ingest",
        # Razorpay posts subscription/payment events server-to-server signed
        # with X-Razorpay-Signature (no bearer). The handler verifies the HMAC
        # before doing anything; without this entry the auth middleware would
        # 401 every callback and billing lifecycle events would never process.
        "/api/v1/billing/razorpay/webhook",
    ]
)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extract JWT from every request, set tenant/user context on request.state.

    request.state attributes set:
        user_id       (uuid.UUID | None)
        tenant_id     (uuid.UUID | None)
        role          (str | None)
        industry_code (str | None)
        request_id    (str)
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        request.state.request_id = request_id
        request.state.user_id = None
        request.state.tenant_id = None
        request.state.role = None
        request.state.industry_code = None
        request.state.firebase_uid = None

        if self._is_public(request):
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        token = self._extract_bearer(request)
        if token is None:
            return self._unauthorized("Authentication required", request_id)

        try:
            # Firebase ID-token verification is a synchronous, potentially
            # network-bound call (signature check + optional revocation lookup).
            # Run it off the event loop so a single blocking verify cannot stall
            # the worker for every other in-flight request.
            if get_settings().firebase_enabled:
                identity = await run_in_threadpool(get_verifier().verify, token)
            else:
                # Dev-token path is pure-CPU JWT decode — no need to offload.
                identity = get_verifier().verify(token)
        except TokenVerificationError as exc:
            log.info("auth.token.rejected", error=str(exc))
            return self._unauthorized("Token is invalid or has expired", request_id)

        try:
            user_id = uuid.UUID(identity["puid"])
            tenant_id = uuid.UUID(identity["tid"])
        except (KeyError, ValueError):
            return self._unauthorized("Token is invalid", request_id)
        role = identity["role"]
        industry_code = identity["ind"]
        allowed_industries = identity.get("industries")

        # Allow workspace switching without re-login — but only to an industry
        # the tenant is actually subscribed to. The user's own active industry
        # is always permitted; any other value must appear in the token's
        # `industries` claim, else we reject (deny-by-default).
        override = request.headers.get("X-Industry-Code")
        if override:
            try:
                requested = IndustryCode(override).value
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": f"Unknown industry code: {override}"},
                    headers={"X-Request-ID": request_id},
                )
            if requested != industry_code:
                if not allowed_industries or requested not in allowed_industries:
                    log.warning(
                        "auth.industry_switch.denied",
                        requested=requested,
                        allowed=allowed_industries,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": f"Industry '{requested}' is not enabled for this tenant"
                        },
                        headers={"X-Request-ID": request_id},
                    )
            industry_code = requested

        request.state.user_id = user_id
        request.state.tenant_id = tenant_id
        request.state.role = role
        request.state.industry_code = industry_code
        request.state.firebase_uid = identity.get("uid")

        structlog.contextvars.bind_contextvars(
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            role=role,
            industry=industry_code,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _unauthorized(detail: str, request_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": detail},
            headers={"WWW-Authenticate": "Bearer", "X-Request-ID": request_id},
        )

    @staticmethod
    def _is_public(request: Request) -> bool:
        path = request.url.path
        if path in _PUBLIC_PATHS:
            return True
        if path.startswith("/static/"):
            return True
        return False

    @staticmethod
    def _extract_bearer(request: Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and len(auth) > 7:
            return auth[7:]
        return None
