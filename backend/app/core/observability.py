"""Observability: Prometheus metrics + OpenTelemetry tracing.

We expose:
  • prometheus_client metrics at GET /metrics
  • OpenTelemetry traces over OTLP/gRPC to the configured collector
  • A custom HTTP middleware that records request count / latency / errors,
    labelled by route template, method, status, and tenant_id where present.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from app.config import Settings

log = structlog.get_logger(__name__)

# Dedicated registry so we can run multiple workers without clashing on the
# default global registry's metrics during test runs.
REGISTRY = CollectorRegistry(auto_describe=True)

http_requests_total = Counter(
    "sanket_http_requests_total",
    "Total HTTP requests handled by the API.",
    labelnames=("method", "route", "status", "industry"),
    registry=REGISTRY,
)
http_request_duration_seconds = Histogram(
    "sanket_http_request_duration_seconds",
    "Per-request latency histogram.",
    labelnames=("method", "route", "industry"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
http_in_flight = Gauge(
    "sanket_http_in_flight_requests",
    "Requests currently being processed.",
    registry=REGISTRY,
)

db_query_duration_seconds = Histogram(
    "sanket_db_query_duration_seconds",
    "Time spent executing a DB query, by logical operation.",
    labelnames=("operation",),
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
    registry=REGISTRY,
)

forecast_runs_total = Counter(
    "sanket_forecast_runs_total",
    "Forecast runs persisted, by industry & mode.",
    labelnames=("industry", "mode"),  # mode: trained | zero_shot
    registry=REGISTRY,
)

gxp_batch_actions_total = Counter(
    "sanket_gxp_batch_actions_total",
    "GxP batch state transitions (release, reject, recall).",
    labelnames=("action", "result"),
    registry=REGISTRY,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records prometheus metrics for every HTTP request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip /metrics itself so it doesn't count its own scrape requests.
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        http_in_flight.inc()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            http_in_flight.dec()
            elapsed = time.perf_counter() - start
            route = _resolve_route_template(request)
            industry = getattr(request.state, "industry_code", "_none") or "_none"
            http_requests_total.labels(
                method=request.method,
                route=route,
                status=str(status),
                industry=industry,
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                route=route,
                industry=industry,
            ).observe(elapsed)


def _resolve_route_template(request: Request) -> str:
    """Use the FastAPI route template, not the raw path, so per-id requests
    aggregate into a single time series."""
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path


def configure_observability(app: FastAPI, settings: Settings) -> None:
    """Wire Prometheus + (optional) OpenTelemetry into the FastAPI app."""
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """Prometheus metrics scrape endpoint.

        Protected by METRICS_TOKEN if set — pass it as:
          Authorization: Bearer <token>
          or X-Metrics-Token: <token>

        In production without a token configured, access is denied.
        In development without a token, access is allowed with a warning logged.
        """
        metrics_token = getattr(settings, "metrics_token", None) or None
        if metrics_token:
            auth_header = request.headers.get("Authorization", "")
            x_token = request.headers.get("X-Metrics-Token", "")
            provided = (
                auth_header.removeprefix("Bearer ").strip()
                if auth_header.startswith("Bearer ")
                else x_token.strip()
            )
            import hmac as _hmac

            if not provided or not _hmac.compare_digest(provided, metrics_token):
                return Response(status_code=401, content="Unauthorized")
        elif settings.is_production:
            # No token in production — reject to avoid data exposure.
            log.warning(
                "metrics.unprotected_in_production",
                note="Set METRICS_TOKEN to protect this endpoint",
            )
            return Response(status_code=403, content="Forbidden: METRICS_TOKEN not configured")
        return PlainTextResponse(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    # OpenTelemetry — only enabled when the OTLP endpoint is set so dev
    # environments without a collector don't pay the cost.
    otlp_endpoint = getattr(settings, "otlp_endpoint", None) or None
    if otlp_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create(
                {
                    "service.name": settings.app_name.lower(),
                    "service.version": settings.app_version,
                    "deployment.environment": settings.app_env,
                }
            )
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
            )
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
            SQLAlchemyInstrumentor().instrument()
            log.info("otel.configured", endpoint=otlp_endpoint)
        except ImportError:
            log.warning(
                "otel.skipped",
                msg="opentelemetry-* packages not installed; tracing disabled.",
            )
        except Exception as exc:
            log.error("otel.setup.failed", error=str(exc))
    else:
        log.info("otel.disabled", reason="OTLP_ENDPOINT not set")
