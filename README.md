# SANKET — Enterprise Multi-Industry Predictive Analytics & Supply Chain SaaS

A vertically-integrated SaaS platform delivering predictive forecasting and supply-chain
optimization for three verticals: **Apparel & Fashion**, **Consumer Electronics**, and
**Pharmaceuticals** (GxP / 21 CFR Part 11 compliant).

```
┌────────────────────────────────────────────────────────────────────┐
│                       SANKET Platform                              │
├─────────────────┬──────────────────────────┬───────────────────────┤
│   React SPA     │   FastAPI Backend        │    ML Inference API   │
│   (port 5173)   │   (port 8000)            │    (port 8001)        │
│                 │   • Multi-tenant RLS     │    • Trained ensemble │
│                 │   • Industry router      │    • Chronos zero-shot│
│                 │   • GxP batch audit      │    • Per-SKU routing  │
└────────┬────────┴────────────┬─────────────┴──────────┬────────────┘
         │                     │                        │
         └─────────────────────┴────────┬───────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │  PostgreSQL 16 +   │
                              │  pgvector + RLS    │
                              └────────────────────┘
```

## Repository layout

| Path | Purpose |
|------|---------|
| `index.html` | Marketing landing page |
| `backend/` | FastAPI app, SQL schema, Alembic migrations, tests |
| `backend/ml/` | Forecasting stack (foundation, deep, GBT, statistical), causal, optimization, inference API |
| `frontend/` | Vite + React + TypeScript dashboard |
| `infra/` | Docker Compose, Kubernetes manifests, Prometheus, Grafana |
| `docs/` | Architecture, runbook, operations |
| `.github/workflows/` | CI/CD pipelines |

## Quick start (local)

```bash
cp .env.example .env
docker compose up -d --build
# Wait for ml-api to preload Chronos (~60–90s)

# UI:           http://localhost:8080
# Backend:      http://localhost:8000/docs
# ML API:       http://localhost:8001/health
# Prometheus:   http://localhost:9090
# Grafana:      http://localhost:3000 (anonymous viewer or admin/sanket)
```

Seed the dev tenant + run a first training pass:

```bash
docker compose exec postgres psql -U sanket_app -d sanket -f /docker-entrypoint-initdb.d/004_seed.sql
docker compose exec ml-api python -m scripts.train_all
```

## Phase summary

| Phase | Files | Deliverable |
|------:|------:|-------------|
| 0 | 1 | Marketing landing page (`index.html`) |
| 1 | 44 | PostgreSQL schema (RLS, ENUMs, partitioned tables, pgvector) + FastAPI multi-tenant backend |
| 2 | 52 | Foundation / deep / GBT / statistical models + 5-stage training + causal + supply-chain optimization + inference API |
| 3 | 54 | React dashboard wired to both APIs |
| 3.5 | 4 | Zero-shot Chronos fallback in inference API |
| 4 | ~30 | Docker, Compose, K8s, CI/CD, Prometheus, Grafana, Alembic, tests, docs |

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, data flow, multi-tenancy model
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — common incidents and how to recover
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — day-to-day operator playbook (deploys, migrations, scaling)

## License

Proprietary. © SANKET.
