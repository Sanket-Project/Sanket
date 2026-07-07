from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Known-weak defaults that must never reach production
_WEAK_JWT_SECRETS = {
    "dev-secret-please-rotate-in-prod-min-32-chars",
    "changeme",
    "secret",
    "password",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "SANKET"
    app_version: str = "0.1.0"
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = False
    # NoDecode: stop pydantic-settings from JSON-decoding this list field at the
    # source level (which fails on a bare value like "https://app.example") and
    # let parse_origins handle both JSON arrays and comma-separated strings.
    allowed_origins: Annotated[list[str], NoDecode] = Field(default=["http://localhost:3000"])

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://sanket_app:changeme@localhost:5432/sanket"
    )
    db_pool_size: int = Field(default=20, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=50)
    db_pool_timeout: int = Field(default=30, ge=5)
    db_echo: bool = False
    # Set True when DATABASE_URL points at PgBouncer in *transaction* pooling
    # mode. asyncpg uses server-side prepared statements by default, which break
    # under transaction pooling (a statement prepared on one server connection is
    # reused on another). This disables the statement cache so the app is
    # pooler-safe. Our per-request tenant GUC uses SET LOCAL inside an explicit
    # transaction, so it is already transaction-pooling-safe (no GUC leakage).
    db_pgbouncer_mode: bool = False

    # ── JWT ──────────────────────────────────────────────────────────────────
    # In Firebase mode the request bearer is a Firebase ID token verified with
    # Google's public keys. The jwt_secret below is only used to sign/verify the
    # local dev-fallback identity tokens when Firebase is not configured.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    jwt_refresh_token_expire_days: int = Field(default=30, ge=1, le=90)

    # ── Firebase Authentication ──────────────────────────────────────────────
    # When either of these is set, the backend verifies real Firebase ID tokens.
    # When both are empty (local dev), the dev-fallback identity provider is used
    # (POST /auth/dev-login issues HS256 tokens in the same claim shape).
    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None  # path to service-account JSON (local dev only)
    # Preferred for production/Cloud Run: base64-encoded service-account JSON.
    # Generate: base64 -w0 path/to/firebase-credentials.json
    # This avoids hardcoded filesystem paths that break in containers.
    firebase_credentials_json: str | None = None
    firebase_web_api_key: str | None = None  # optional, surfaced to clients
    # When True, every request verifies the ID token against Firebase's
    # revocation list. This is a signature+revocation check; the result is cached
    # for `firebase_revocation_cache_ttl_s` so we do not pay a Firebase
    # round-trip on every single request (which would couple request latency to
    # Firebase availability). Phase 1 hardening defaults this ON so a
    # deprovisioned/compromised user is cut off within the cache TTL instead of
    # surviving for the full ~1h ID-token lifetime.
    firebase_check_revoked: bool = False
    # How long a successful revocation check is trusted before re-verifying.
    # 0 disables caching (check on every request — strongest, slowest).
    firebase_revocation_cache_ttl_s: int = Field(default=60, ge=0, le=3600)

    # ── Public demo sandbox ──────────────────────────────────────────────────
    # The marketing site's "Try the Sandbox" button authenticates a shared,
    # read-only demo account *server-side* so no credentials ship in the browser
    # bundle. The password is never referenced here — in dev mode the backend
    # mints a dev token directly, and in Firebase mode it mints a custom token —
    # so the demo account can (and should) have no usable password at all.
    #
    # SECURITY: this MUST point at a dedicated *viewer*-role user, never the
    # tenant owner/admin. Anyone on the internet can start a sandbox session, so
    # the account it maps to defines the blast radius. The seed provisions
    # `sandbox@sanket-dev.com` with UserRole.viewer precisely so an anonymous
    # visitor cannot mutate shared demo data, manage members, or touch billing.
    sandbox_enabled: bool = True
    sandbox_tenant_slug: str = "sanket-dev"
    sandbox_email: str = "sandbox@sanket-dev.com"

    # ── Integrations (Shopify, etc.) ─────────────────────────────────────────
    # Symmetric secret used to encrypt third-party access tokens at rest. Any
    # string works (a Fernet key is derived from it via SHA-256). Falls back to
    # jwt_secret when unset so local dev works without extra config.
    integration_encryption_key: str | None = None
    # Shopify Admin API version to pin requests to (YYYY-MM). Bump quarterly.
    shopify_api_version: str = "2024-10"
    # Near-real-time sales polling for connected Shopify stores.
    shopify_poll_enabled: bool = True
    shopify_poll_interval_s: int = Field(default=300, ge=60)
    # Public HTTPS base URL Shopify can reach for webhooks (e.g. an ngrok or
    # deployed host). When set, webhooks are auto-registered on connect; unset
    # (local dev) falls back to polling only.
    public_webhook_base_url: str | None = None

    # ── Security ─────────────────────────────────────────────────────────────
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost: int = Field(default=65536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1)

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ── Features ─────────────────────────────────────────────────────────────
    timescaledb_enabled: bool = False

    # ── Observability ────────────────────────────────────────────────────────
    otlp_endpoint: str | None = None  # e.g. "http://otel-collector:4317"
    metrics_enabled: bool = True
    # Bearer token required to scrape GET /metrics. Passed as:
    #   Authorization: Bearer <token>  OR  X-Metrics-Token: <token>
    # Leave blank in dev. REQUIRED in production (the endpoint auto-rejects without one).
    # Generate: openssl rand -hex 24
    metrics_token: str | None = None
    # Secret for GET /health/detailed used by internal ops tooling (sidecars, runbooks).
    # Passed as X-Internal-Token header. Leave blank to restrict to authenticated users only.
    ops_health_token: str | None = None

    # ── Rate limiting ────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 600  # per IP per minute on /api/*
    # Number of trusted reverse-proxy / load-balancer hops in front of the app.
    # The client IP is taken as the Nth-from-rightmost entry of X-Forwarded-For
    # so callers cannot spoof their IP by injecting extra header values.
    # 0 = ignore X-Forwarded-For entirely and trust only the socket peer.
    trusted_proxy_count: int = 1

    # ── Real-time / Redis ────────────────────────────────────────────────────
    redis_url: str | None = None  # e.g. redis://redis:6379/0; None = in-process only

    # ── API response cache ───────────────────────────────────────────────────
    # Read-heavy, tenant-scoped dashboard endpoints (sales analytics) recompute
    # the same aggregates on every poll. When Redis is configured we cache the
    # JSON response for a short TTL, keyed per tenant + endpoint + params and
    # versioned per tenant so a write (e.g. a new sale) invalidates the whole
    # tenant's cache at once. With no Redis this is a transparent no-op.
    api_cache_enabled: bool = True
    api_cache_ttl_s: int = Field(default=30, ge=1, le=3600)

    # ── Multi-region ─────────────────────────────────────────────────────────
    deploy_region: str = "us-east"  # cell identifier for this deployment

    # ── Billing (Razorpay) ───────────────────────────────────────────────────
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    # Billing cycles a new subscription runs for before completing (Razorpay
    # requires a finite total_count; ~10 years of monthly billing).
    razorpay_total_count: int = 120

    # ── Webhook delivery ─────────────────────────────────────────────────────
    webhook_retry_worker_enabled: bool = True
    webhook_retry_interval_s: int = 30

    # ── Inbound webhook replay protection ────────────────────────────────────
    # Inbound provider webhooks (Shopify, Razorpay) are authenticated by HMAC
    # but a captured-and-replayed body would still pass the signature check. We
    # additionally (a) reject deliveries whose timestamp is outside a freshness
    # window and (b) record each delivery id in Redis so a duplicate is dropped.
    webhook_replay_protection_enabled: bool = True
    webhook_replay_max_age_s: int = Field(default=300, ge=30, le=3600)
    # How long a seen delivery-id is remembered (>= max_age so the window can't
    # be beaten by waiting out the dedupe key).
    webhook_replay_dedupe_ttl_s: int = Field(default=900, ge=60)

    # ── Request idempotency ──────────────────────────────────────────────────
    # When a mutating request carries an `Idempotency-Key` header, the first
    # response is cached in Redis and replayed for any retry with the same key
    # (scoped per tenant + method + path) so client retries / proxy retries do
    # not double-charge or double-create.
    idempotency_enabled: bool = True
    idempotency_ttl_s: int = Field(default=86400, ge=60)  # 24h

    # ── Background-worker leader election ────────────────────────────────────
    # Singleton background loops (signal ingest, Shopify poller, webhook retry)
    # must run on exactly ONE replica or they duplicate external API polling and
    # webhook retries. A Redis lease lock elects a single leader; the lease is
    # renewed on an interval and auto-expires if the leader dies. With no Redis
    # (single-node dev) every loop simply runs in-process as before.
    worker_leader_lock_ttl_s: int = Field(default=30, ge=5)
    worker_leader_renew_interval_s: int = Field(default=10, ge=2)

    # ── Phase 6: external signal ingestion ───────────────────────────────────
    signal_pipeline_enabled: bool = True
    signal_pipeline_interval_s: int = 900  # 15 min default
    fred_api_key: str | None = None  # optional, falls back to synthetic
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    # RSS — no key required; connector uses feedparser with public feed URLs
    rss_extra_feeds_fashion: str | None = None  # JSON list of extra feed URLs
    rss_extra_feeds_electronics: str | None = None
    rss_extra_feeds_pharma: str | None = None
    rss_extra_feeds_agrocenter: str | None = None
    rss_extra_feeds_hardware: str | None = None
    serpapi_key: str | None = None
    # Pinterest Trends — requires a Pinterest business access token (OAuth2 Bearer)
    pinterest_access_token: str | None = None

    # ── Phase 7: ML inference service URL ────────────────────────────────────
    ml_api_url: str = "http://localhost:8001"
    # Shared secret presented to the internal ML inference service as a bearer
    # token. The ML service rejects any request without it (fail-closed), so a
    # browser or other untrusted caller can no longer reach the tenant-scoped
    # forecast endpoints directly. Required in production; falls back to
    # jwt_secret in dev so the local stack works without extra config.
    ml_service_token: str | None = None
    # Chronos-t5-large zero-shot inference can take ~60s+ on CPU. Keep this
    # comfortably above observed latency so the real ML baseline actually
    # completes instead of timing out and silently falling back to synthetic.
    ml_api_timeout_s: float = 120.0

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            s = v.strip()
            # Accept a JSON array (docker-compose style) or a comma-separated
            # string (".env"/k8s style, including a single bare origin).
            if s.startswith("["):
                import json

                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(o).strip() for o in parsed if str(o).strip()]
                except ValueError:
                    pass
            return [o.strip() for o in s.split(",") if o.strip()]
        return v

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def reject_weak_jwt_secret(cls, v: str, info) -> str:  # type: ignore[override]
        app_env = (info.data or {}).get("app_env", "development")
        if app_env == "production" and v in _WEAK_JWT_SECRETS:
            raise ValueError(
                "jwt_secret is set to a known-weak development value. "
                "Generate a strong secret: openssl rand -hex 32"
            )
        if v in _WEAK_JWT_SECRETS:
            import structlog as _structlog

            _structlog.get_logger(__name__).warning(
                "config.jwt_secret.weak_default",
                note="Replace JWT_SECRET before deploying to production",
            )
        return v

    @model_validator(mode="after")
    def require_firebase_in_production(self) -> Settings:
        """The local dev identity fallback must never be active in production."""
        if self.app_env == "production" and not self.firebase_enabled:
            raise ValueError(
                "Firebase is not configured (FIREBASE_PROJECT_ID / "
                "FIREBASE_CREDENTIALS_PATH) but APP_ENV=production. The local "
                "dev-login fallback is disabled in production — configure Firebase."
            )
        return self

    @model_validator(mode="after")
    def reject_weak_secrets_in_production(self) -> Settings:
        """Fail-closed on known-weak / default secrets when APP_ENV=production.

        These are the footguns that quietly ship to prod: the seeded ``changeme``
        DB password, an unset metrics token (which would leave /metrics open if
        the auth check were ever relaxed), and the ML service token falling back
        to the JWT secret. Catching them at startup beats discovering them in an
        incident. Non-production environments only warn so local/staging keep
        working with defaults.
        """
        problems: list[str] = []
        if ":changeme@" in self.database_url:
            problems.append("DATABASE_URL still uses the default 'changeme' password")
        if self.metrics_enabled and not self.metrics_token:
            problems.append("METRICS_TOKEN is unset (the /metrics endpoint must be token-gated)")
        if not self.ml_service_token:
            problems.append(
                "ML_SERVICE_TOKEN is unset — it would fall back to JWT_SECRET; set a distinct secret"
            )
        if not self.integration_encryption_key:
            problems.append(
                "INTEGRATION_ENCRYPTION_KEY is unset — third-party tokens would be encrypted "
                "with a key derived from JWT_SECRET; set a dedicated key"
            )

        if not problems:
            return self
        detail = "; ".join(problems)
        if self.app_env == "production":
            raise ValueError(f"Refusing to start in production with weak secrets: {detail}")
        import structlog as _structlog

        _structlog.get_logger(__name__).warning(
            "config.secrets.weak", detail=detail, note="Must be fixed before production deploy"
        )
        return self

    @property
    def firebase_enabled(self) -> bool:
        """True when real Firebase credentials are configured.

        When False the backend falls back to the local dev identity provider
        so the app still runs end-to-end without a Firebase project.
        """
        return bool(self.firebase_project_id or self.firebase_credentials_path)

    @property
    def ml_service_token_effective(self) -> str:
        """Bearer presented to the ML service. Falls back to jwt_secret in dev
        so the local stack authenticates without extra config; production sets
        ML_SERVICE_TOKEN explicitly (and the ML service reads the same value)."""
        return self.ml_service_token or self.jwt_secret

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
