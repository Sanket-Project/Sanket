"""Attach defensive HTTP security headers to every response.

The static frontend gets headers from nginx, but API/JSON responses are served
directly by FastAPI and previously carried none. This middleware closes that gap
so browsers enforce framing, MIME-sniffing, referrer and transport protections
on API responses too.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# A strict default-deny CSP. The API returns JSON, not HTML, so it needs no
# script/style sources; `frame-ancestors 'none'` also blocks clickjacking for
# any HTML error pages. The SPA's own (looser) CSP lives in nginx.conf.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

_STATIC_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": _API_CSP,
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _STATIC_HEADERS.items():
            response.headers.setdefault(header, value)
        # HSTS only in production (behind TLS) — never on plain-HTTP dev.
        if self._enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return response
