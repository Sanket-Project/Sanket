# SANKET Architecture

## Components

```
┌──────────────────────────────────────────────────────────────────┐
│                    Ingress (nginx, TLS termination)              │
└─────────┬──────────────────────┬─────────────────────────────────┘
          │ /                    │ /api/         /ml/
┌─────────▼─────────┐  ┌─────────▼──────────┐  ┌──────────────────┐
│   frontend        │  │   backend (FastAPI)│  │  ml-api (FastAPI)│
│   nginx + React   │  │   :8000            │  │  :8001           │
│   :8080           │  │   • auth           │  │  • Chronos       │
└───────────────────┘  │   • industry router│  │    zero-shot     │
                       │   • CRUD + signals │  │  • trained       │
                       │   • GxP batches    │  │    ensemble      │
                       │   • RLS scoped DB  │  │    (joblib)      │
                       └─────┬──────────────┘  └─────┬────────────┘
                             │                       │
                             └────────────┬──────────┘
                                          │
                                 ┌────────▼─────────┐
                                 │  PostgreSQL 16   │
                                 │  + pgvector      │
                                 │  + RLS policies  │
                                 └──────────────────┘
```

## Multi-tenancy model

- **Logical tenant boundary** = `tenant_id` UUID on every domain table.
- **Enforcement** = PostgreSQL RLS policy `tenant_id = current_tenant_id()`,
  driven by `SET LOCAL app.current_tenant_id = '<uuid>'` set inside every
  async session opened by the application.
- **Token claim** = JWT carries `tid` (tenant_id), `ind` (active industry),
  `role`. The `TenantContextMiddleware` extracts these and writes them to
  `request.state`, which both routers and the DB session helper read.
- **Workspace switching** = the SPA sends `X-Industry-Code: pharma` to
  override the JWT-default industry for that single request.

## Industry verticals

Each vertical declares an `IndustryContext` (`backend/app/services/industry_context.py`)
with: SKU attribute schema, default forecast horizon, required signal types,
forecast/optimization model lists, and audit level. The router layer
dispatches per-vertical endpoints (`/fashion/*`, `/electronics/*`, `/pharma/*`)
and the ML training pipeline reads from the same registry.

## Data flow — forecast request

```
client ──POST /forecast──> ml-api
                              │
                              ├── artifact exists? ──yes──> InferenceService
                              │                              ├── load joblib bundles
                              │                              ├── run StackedEnsemble
                              │                              └── persist forecast_results
                              │
                              └── no  ──> ZeroShotForecaster
                                          ├── pull history (RLS) OR series_context
                                          ├── Chronos pipeline.predict()
                                          ├── empirical p10/p50/p90
                                          └── persist forecast_results
```

Both paths return a `ForecastResponse` with a `source` discriminator so the UI
can tell trained from zero-shot.

## ML training methodology (5-stage)

1. **DATA** — `HistoricalSalesLoader.load()` pulls panel, intermittency-classifies.
2. **PRE-TRAIN** — registry instantiates foundation/deep/GBT/statistical models per industry.
3. **DOMAIN FIT** — `pipeline.run()` trains each model on the tenant's panel.
4. **STACK** — `StackedEnsemble.fit()` solves SLSQP to minimize pinball loss
   on the holdout window → convex weights.
5. **VALIDATE** — walk-forward backtest + holdout report → MLflow.

## Observability

| Signal | Source | Destination |
|--------|--------|-------------|
| Structured logs | `structlog` JSON | stdout → Loki/CloudWatch |
| Metrics | `prometheus_client` | `/metrics` → Prometheus → Grafana |
| Traces | OTLP/gRPC (optional) | OpenTelemetry Collector |
| Audit trail | `audit_log` table (append-only via SQL RULE) | postgres |
| MLflow runs | `mlflow` SDK | volume-mounted file backend |

## Security posture

- argon2id password hashing (configurable cost)
- JWT HS256, 60-minute access tokens, 30-day refresh with rotation
- Refresh tokens: only sha256 hash stored DB-side
- RLS on every tenant-scoped table; `sanket_app` role has no superuser rights
- `audit_log` is append-only via PostgreSQL RULE — UPDATE/DELETE NO-OP
- GxP-mode (pharma) enforces additional constraints: QA-release requires
  admin/owner role + cold-chain temperature presence checks + immutable audit
- Container security context: non-root, read-only rootfs, all caps dropped
- NetworkPolicy: default deny, explicit allow only between adjacent tiers
