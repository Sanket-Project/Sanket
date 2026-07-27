# 01 — Codebase Map

**Date:** 2026-07-26
**Method:** static read-only review. No files modified, nothing committed.
**Conventions:** every claim cites `path:line`. Anything I inferred rather than
verified is tagged **[ASSUMPTION]**.

---

## 1. Stack and deployment

| Layer | Technology | Evidence |
|---|---|---|
| API | FastAPI, Python ≥3.12 | `backend/pyproject.toml:9` |
| ORM | SQLAlchemy 2.0 async + asyncpg | `backend/pyproject.toml:16-17` |
| Migrations | Alembic (18 revisions) + 13 raw SQL bootstrap files | `backend/alembic/versions/`, `backend/sql/` |
| DB | PostgreSQL 16 + pgvector, RLS, declarative partitioning | `backend/sql/001_extensions.sql`, `sql/006_phase6_trends_alerts.sql:71-78` |
| Cache / queue | Redis, `arq` job queue | `backend/pyproject.toml:56,59` |
| Auth | Firebase Admin SDK, with a dev-login JWT fallback | `backend/app/core/firebase_auth.py`, `.env.example:12-24` |
| Payments | **Razorpay** (migrated off Stripe in `alembic/versions/0010_stripe_to_razorpay.py`) | `backend/pyproject.toml:57` |
| Frontend | Vite + React + TypeScript + Tailwind, TanStack Query, Zustand | `frontend/package.json` |
| ML | Separate inference API on :8001 (Chronos, GBT, deep, statistical) | `README.md`, `backend/ml/` |
| Observability | Prometheus client, structlog, Grafana | `backend/pyproject.toml:44,38` |

**Backend size:** 21,954 LOC across 130 Python modules in `backend/app/`.

### Deployment

- **Local:** `docker compose up -d --build` — UI :8080, API :8000, ML :8001,
  Prometheus :9090, Grafana :3000 (`README.md`, `docker-compose.yml`).
- **CI/CD:** 7 GitHub Actions workflows (`.github/workflows/`). Images build and
  scan on `main`, then **staging deploys automatically**; production is
  `workflow_dispatch` only (`deploy.yml:29,40-42`).
- **Target:** GKE via kustomize overlays, namespace `sanket-staging` /
  `sanket-production` (`deploy.yml:99-101,122`).
- **Regions:** a `regions` table and `RegionRouterMiddleware` exist
  (`sql/005_phase5_realtime_billing.sql:9`, `app/middleware/region_router.py`),
  so multi-region is at least scaffolded. See `docs/MULTI_REGION.md`.

---

## 2. Multi-tenancy model

**Isolation strategy: shared schema, PostgreSQL row-level security.** Not
schema-per-tenant, not database-per-tenant.

### How tenant context is resolved

1. `TenantContextMiddleware.dispatch` (`app/middleware/tenant_context.py:64`)
   runs on every request. A frozen allowlist of public paths bypasses it
   (`tenant_context.py:18-50`) — health, docs, signup, dev-login,
   sandbox-session, and three webhook receivers that authenticate themselves.
2. The bearer token is verified — Firebase ID token in prod (offloaded to a
   threadpool at `tenant_context.py:93`), a locally-signed dev JWT otherwise.
3. `puid` / `tid` / `role` / `ind` claims are pulled off the token and written to
   `request.state` (`tenant_context.py:102-107, 140-144`).
4. An `X-Industry-Code` header can switch the active workspace, but only to an
   industry present in the token's `industries` claim — deny-by-default
   (`tenant_context.py:114-138`). This is correctly implemented.

### How it reaches the database

`Database.session(tenant_id)` opens a transaction and issues
`set_config('app.current_tenant_id', :tid, true)` (`app/core/database.py:83-86`).
`LOCAL` scoping means pool reuse is safe. Every RLS policy reads
`current_tenant_id()` (`sql/003_rls_policies.sql:11-13`).

There is a second door: `Database.session_no_rls()` sets
`app.bypass_rls = 'true'` (`database.py:102`), and every policy is written as
`USING (bypass_rls() OR tenant_id = current_tenant_id())`
(`sql/003_rls_policies.sql:43-127`). This is a deliberate escape hatch for
cross-tenant background work, but it means **isolation is one wrong
`session_no_rls()` call away from being void**. Current callers:

- `seed_database_if_empty` (`database.py:270`) — fine.
- `list_plans` (`app/routers/billing.py:92`) — `plans` is a global table, so
  correct in effect, but a heavier hammer than needed.
- `razorpay_webhook` (`app/routers/billing.py:357`) — necessary; the webhook has
  no tenant context until the subscription row is found.

### Defence in depth that is genuinely good

- `assert_tenant_isolation_enforced` (`database.py:116-175`) refuses to boot in
  production if the DB role is `SUPERUSER` or has `BYPASSRLS`, or if `tenants`
  lacks `FORCE ROW LEVEL SECURITY`. This closes the single most common
  RLS footgun (pointing `DATABASE_URL` at a managed provider's admin role).
- Migration `0011_reconcile_schema_and_force_rls.py:155` applies
  `FORCE ROW LEVEL SECURITY` to every RLS-enabled table, so the table owner is
  also subject to policy.
- `backend/tests/test_rls_isolation.py` exists and exercises this.

---

## 3. Auth, roles, permissions

**Roles (highest → lowest):** `owner`, `admin`, `analyst`, `viewer`
(`app/core/rbac.py:20-30`).

Two dependency factories (`app/core/rbac.py`):

- `require_role(roles)` — trusts the JWT claim, no DB hit (`rbac.py:47`).
- `require_role_db(roles)` — additionally re-reads the user's current role from
  the DB, closing the ~1h window where a demoted admin keeps access
  (`rbac.py:79`). Fails **closed** if the DB is unreachable (`rbac.py:124-128`).

Prebuilt: `require_admin`, `require_owner`, `require_admin_db`,
`require_owner_db` (`rbac.py:155-159`).

**Auth entry points** (`app/routers/auth.py`): signup, google-signup, dev-login,
session, config, sandbox-session. The sandbox account is deliberately seeded as
`viewer`, not admin (`database.py:322-333`) — correct, since anyone on the
internet can mint that session.

Supporting controls: brute-force lockout (`app/core/login_attempt.py`), rate
limiting (`app/middleware/rate_limit.py`), idempotency keys
(`app/middleware/idempotency.py`), security headers with HSTS in prod
(`app/main.py:296`), Argon2 password hashing (`pyproject.toml:29`).

---

## 4. Billing and payments — detailed

This is the newest and least-trusted layer, so it gets the most space. Two prior
reviews exist in the repo root (`PAYMENT_AUDIT.md`, `PAYMENT_REVIEW_ROUND2.md`,
both dated 2026-07-21) and many of their P0s have been fixed in source. What
follows is the **current** state.

### Provider

Razorpay, via `app/services/billing/razorpay_client.py`. Migrated from Stripe in
`alembic/versions/0010_stripe_to_razorpay.py`.

### Plan definitions

`plans` table (`sql/005_phase5_realtime_billing.sql:48`), modelled at
`app/models/billing.py:34-55`. Columns: `base_price_cents`, `billing_interval`,
`razorpay_plan_id`, `trial_days`, `included_quotas` (JSONB),
`overage_rates_cents` (JSONB).

Seeded plans: `growth_monthly`, `growth_yearly`, `scale_monthly`,
`scale_yearly`, `enterprise_monthly` (`sql/005:61`).
Migration `0017_billing_p0_guards.py:66` runs
`UPDATE plans SET trial_days = 14 WHERE base_price_cents > 0` — **every priced
plan carries a 14-day trial.**

### Checkout flow

1. `POST /billing/subscription` (`app/routers/billing.py:135`), guarded by
   `require_admin_db`.
2. `SubscriptionManager.start_subscription` (`subscription_manager.py:75`):
   - Enforces one live subscription per tenant (`:99-118`), backed by a partial
     unique index from migration 0017.
   - Trial length comes from `plan.trial_days`, never the caller (`:125`) — the
     old caller-supplied `trial_days` hole is closed (`billing.py:45-50`).
   - Refuses to activate a priced plan with no `razorpay_plan_id` (`:133-144`).
     This is the fix for the "priced plan silently marked active with no payment"
     bug.
3. Frontend opens the Razorpay JS checkout, falling back to the hosted
   `short_url` (`SubscriptionGate.tsx:128-159`), with a host allowlist on the
   redirect (`SubscriptionGate.tsx:15-34`).
4. `POST /billing/subscription/verify` (`billing.py:196`) →
   `verify_and_activate` (`subscription_manager.py:226`), which checks the
   signature **and then** fetches the payment to confirm
   `status == "captured"` (`:270`), that the payment belongs to this
   subscription (`:283`), and that the amount covers the plan price (`:296`).
   This is well done.

`return_path` is validated as a relative path and joined to a server-owned
origin (`billing.py:52-62,150`), closing the callback-hijack hole.

### Webhook handling

`POST /billing/razorpay/webhook` (`billing.py:318`), unauthenticated but
HMAC-verified (`:327`), with replay protection: staleness window + Redis dedupe
on the provider event id (`:337-353`, `app/core/webhook_replay.py`).

`handle_razorpay_event` (`subscription_manager.py:327`) applies events with:

- An out-of-order guard using `last_event_ts` in `metadata`
  (`:350-361`) — prevents a delayed `activated` from resurrecting a cancelled sub.
- Entity status as source of truth, event type only as tiebreaker
  (`:379-396`).
- Termination events outranking the entity (`:403-406`).

Realtime notifications are buffered and only flushed after commit
(`_queue_notify` `:485`, `flush_notifications` `:512`) — a genuinely good fix.

### Subscription state machine

`SubscriptionStatus`: `trialing`, `active`, `past_due`, `paused`, `cancelled`,
`incomplete` (`app/models/billing.py:17-24`).
Razorpay → internal mapping at `subscription_manager.py:46-56`.
`LIVE_STATUSES = (trialing, active, past_due)` (`:37-41`).

### What is **missing** from the billing layer

These are gaps, not bugs — verified by absence:

| Missing | Evidence |
|---|---|
| **Upgrade / downgrade / plan switch** | `PlanChangeNotSupportedError` raised unconditionally at `subscription_manager.py:113-117`. The UI offers "Switch to this plan" and it 409s. |
| **Proration** | No proration logic anywhere in `app/services/billing/`. |
| **Invoices** | No `Invoice` model, no `invoices` table, no invoice endpoint. `grep -i invoice app/` returns only comments and CSV column aliases. |
| **Receipts** | Same. |
| **Email notifications** | No mail transport anywhere in the billing path. |
| **A real billing portal** | `POST /billing/portal` (`billing.py:251`) returns the Razorpay subscription `short_url`, not a portal. Acknowledged in the code comment at `:258`. |
| **Tax / GST** | No tax handling. Prices are ₹-denominated (`SubscriptionGate.tsx:402`) so Indian GST is presumably in scope. **[ASSUMPTION]** |
| **Dunning / failed-payment recovery** | `payment.failed` sets `past_due` (`:395-396`) and nothing else happens. No retry schedule, no notification, no grace-period expiry job. |

### Billing defects identified statically

Full write-up with severities is in `02-product-walkthrough.md`. Headline:

- **`POST /billing/portal` has no RBAC guard** (`billing.py:251-257`) while every
  other billing mutation carries `require_admin_db`. Any tenant member,
  including a `viewer`, can obtain the subscription management URL.
- **Entitlement is enforced only in React.** `SubscriptionGate` is a
  `.tsx` component (`frontend/src/components/auth/SubscriptionGate.tsx:36`).
  `grep -rn "SubscriptionGate\|require_subscription\|entitle" backend/app/`
  returns **only comments**. There is no server-side subscription check on any
  data endpoint.
- **Trial is burned by an abandoned checkout.** `_trial_available` returns False
  if *any* prior subscription row exists (`subscription_manager.py:480-483`),
  including an `incomplete` row from a checkout the user never completed.
- **Cancel-at-period-end blocks resubscription.** `cancel(at_period_end=True)`
  leaves `status` untouched (`:219-222`), so `_live()` still matches and a
  subsequent `start_subscription` on a different plan raises
  `PlanChangeNotSupportedError`.
- **Prices are hardcoded in the UI.** `SubscriptionGate.tsx:402,447` render
  ₹4,995 / ₹14,995 as literals; the component never calls `/billing/plans`.
  DB, Razorpay, and UI can drift silently.
- **The trial card and the Growth card post the same `plan_id`.**
  `handleSelectPlan("growth_monthly", 14)` (`:380`) vs
  `handleSelectPlan("growth_monthly", 0)` (`:422`) — the second argument is
  cosmetic. Because `plans.trial_days = 14`, a first-time tenant who
  deliberately picks "Select Growth" to pay gets a free trial instead.
- **`_payment_covers_plan` fails open** when the payload omits `amount`
  (`:434-435`). Documented as deliberate; still an entitlement fail-open.

---

## 5. Feature and module inventory

### Complete / production-shaped

| Feature | Path |
|---|---|
| Auth + session + signup + sandbox | `app/routers/auth.py` |
| Tenant/industry routing + workspace switch | `app/routers/industry_router.py`, `app/middleware/tenant_context.py` |
| Products / SKUs | `app/routers/products.py`, `app/routers/skus.py` |
| Forecasts + accuracy + backtest | `app/routers/forecasts.py`, `forecast_accuracy.py` |
| Hybrid forecasting (async, arq) | `app/routers/hybrid_forecast.py`, `app/workers/forecast_worker.py` |
| External signal ingestion (11 connectors) | `app/services/external_signals/` |
| Inventory + shortage alerts | `app/routers/inventory.py`, `shortage_alerts.py` |
| Trends / anomaly / cross-industry | `app/routers/trends.py`, `anomaly.py`, `cross_industry.py` |
| Webhooks out (endpoints + deliveries + retry) | `app/routers/webhooks.py`, `app/services/webhooks.py` |
| Usage metering | `app/middleware/usage_metering.py`, `app/services/usage.py` |
| Realtime (WebSocket) | `app/realtime/`, `app/routers/websocket.py` |
| Integrations: Shopify, WooCommerce, SQL source, file import | `app/services/integrations/` |
| Team invites | `app/routers/invites.py`, migration `0015_team_invites.py` |
| GxP / pharma batch audit | `app/models/pharma.py`, `tests/test_pharma_gxp.py` |

### Half-built

- **Billing.** Subscribe and cancel work; plan change, proration, invoices,
  receipts, dunning, and tax do not (§4).
- **Onboarding.** `app/routers/onboarding.py` exposes only `GET /state` and
  `PUT /state` (`:32,45`). It is a progress-tracker, not a configuration wizard.
  All real setup lives elsewhere.
- **Integrations hub.** `app/connectors/catalog.py` advertises a large connector
  catalogue (Kafka `:496`, AWS `:533`, Snowflake `:570`, Postgres `:661`, MySQL
  `:686`) but only Shopify, WooCommerce, generic SQL, and file import have
  implementations in `app/services/integrations/`. The catalogue is a shop
  window for connectors that mostly don't exist yet. **[ASSUMPTION — I did not
  exhaustively trace every catalogue entry to a handler.]**
- **Enterprise plan.** "Contact Sales" opens a `mailto:` link
  (`SubscriptionGate.tsx:246-248`). No CRM, no lead capture beyond
  `app/routers/demo_request.py`.

### Dead / legacy

- `archive/` — superseded workflows, `legacy/index.html`, old prod config.
- `app/core/firebase.py:13` raises `NotImplementedError` by design; the live
  implementation is `firebase_auth.py`.
- `backend/test_venv/` — a checked-in virtualenv. Should not be in the repo.
- `frontend/vite.config.js.timestamp-*.mjs` — Vite build turd, should be
  gitignored.
- `frontend/node_modules/` and `frontend/dist/` are present in the working tree.

---

## 6. Data model

31 tables. Tenant-scoped tables all carry `tenant_id UUID` and an RLS policy.

### ER summary (tenant-scoped core)

```
tenants ──1:N── users
   │              └── role: owner|admin|analyst|viewer
   ├──1:N── industry_profiles      (per-industry tenant config — see §7)
   ├──1:N── products ──1:N── skus ──1:N── historical_sales  [partitioned quarterly]
   │                           ├──1:N── inventory_levels
   │                           └──1:N── pharma_batches      (pharma only)
   ├──1:N── external_signals ──N:1── signal_clusters
   ├──1:N── trend_signals          [partitioned monthly]
   ├──1:N── forecast_runs ──1:N── forecast_results          [partitioned quarterly]
   ├──1:N── hybrid_forecast_runs
   ├──1:N── alert_rules ──1:N── shortage_alerts
   ├──1:N── integration_connections
   ├──1:N── webhook_endpoints ──1:N── webhook_deliveries
   ├──1:N── usage_events ──rollup──> usage_rollups_daily
   ├──1:N── subscriptions ──N:1── plans          (plans is GLOBAL, not tenant-scoped)
   ├──1:N── invites
   ├──1:N── audit_log
   └──1:N── refresh_tokens

Global: industries, plans, regions, data_quality_issues (tenant_id nullable)
```

Partitioning is automated by `sanket_maintain_partitions()` (migration
`0013_auto_partition_maintenance.py`), called on boot as a backstop
(`database.py:216-241`) with a CronJob as the primary mechanism.

---

## 7. Existing configurability — the Phase 4 foundation

This is the most important section for the customization strategy, so it is
graded honestly.

### What exists today

**`industry_profiles` table** (`sql/002_schema.sql:173`), resolved by
`app/services/industry_config.py:91`. Per tenant, per industry, it stores:

| Field | Type | What it configures |
|---|---|---|
| `custom_horizon_weeks` | int | Overrides the archetype forecast horizon |
| `custom_signal_types` | array | Unioned with archetype-required signal types (`industry_config.py:123-125`) |
| `model_overrides` | JSONB | Passed to the ML layer |
| `feature_flags` | JSONB | General-purpose bag; `feature_flags["focus"]` holds a keyword/category watchlist (`industry_config.py:42-68`) |

**`industry_context.py`** is a **hardcoded Python registry** of five archetypes —
FASHION (`:52`), ELECTRONICS (`:77`), PHARMA (`:102`), AGROCENTER (`:131`),
HARDWARE (`:165`) — each with `default_horizon_weeks` and
`required_signal_types`.

The resolution model is: **hardcoded archetype defaults, narrowed by a per-tenant
profile row.** `resolve_effective_config` (`industry_config.py:91`) merges them
into a frozen `EffectiveIndustryConfig` dataclass. There is no caching layer on
this resolution — it hits the DB on every call. **[ASSUMPTION: I did not trace
every call site to count queries per request.]**

**Per-industry routers** exist for all five verticals
(`app/routers/industries/{fashion,electronics,pharma,agrocenter,hardware}.py`),
wired in `app/main.py:373-377`. Vertical-specific logic today is **code, not
configuration**.

### What does not exist

Verified by absence — these are the gaps Phase 4 must fill:

- **No custom fields or custom objects.** No EAV table, no per-tenant schema
  extension, no JSONB `custom_fields` column on `products` / `skus`.
- **No configurable workflow states.** Forecast run status, alert status, and
  batch status are all Postgres `ENUM`s (`app/models/enums.py`), so a tenant
  cannot rename or add a stage without a migration.
- **No terminology / vocabulary overrides.** UI strings are hardcoded in TSX.
- **No role or permission templates.** Four roles, fixed, in
  `rbac.py:155-159`.
- **No custom forms.** `app/connectors/catalog.py` has a form-field descriptor
  (`AuthField`, `:74`) — this is the closest existing pattern to a
  tenant-definable form and is a reasonable model to generalize.
- **No configurable dashboards or reports.** Pages are fixed React routes.
- **No branding / white-label.** A design-token system exists
  (`design-system/`, `frontend/tailwind.config.ts`, CSS variables like
  `--accent`) so the *mechanism* for theming is present; there is no per-tenant
  binding of it.
- **No notification or template editing.** No template store at all.
- **No industry-specific billing rules.** One global `plans` table; pricing is
  per-tier, not per-vertical, not per-seat/location/usage.
- **No extension point for logic.** No plugin, hook, or scripting surface.

**Net:** the codebase has *one* real configuration axis — the industry profile —
and it is narrow (horizon, signal types, model overrides, a focus watchlist). The
JSONB `feature_flags` bag is the only open-ended surface, and it is undocumented
and unvalidated.

---

## 8. Test coverage and CI

### Tests present

- **Backend:** 24 pytest modules in `backend/tests/`. Notably
  `test_rls_isolation.py`, `test_rbac.py`, `test_billing.py`,
  `test_webhook_replay.py`, `test_pharma_gxp.py`, `test_idempotency.py`. The
  security-critical paths do have coverage.
- **Frontend unit:** only **three** test files —
  `components/ui/Skeleton.test.tsx`, `utils/errors.test.ts`,
  `utils/format.test.ts`. Effectively zero component coverage.
- **E2E:** three Playwright specs — `frontend/e2e/{billing,forecast,login}.spec.ts`.

### CI

`backend-ci.yml`: ruff check, ruff format --check, mypy, pip-audit, pytest with
coverage (`:30,32,34,52,74`).
`frontend-ci.yml`: typecheck, lint, test, build (`:26,28,30,35`).
Plus `ml-ci.yml`, `security.yml`, `build-images.yml`, `deploy.yml`,
`deploy-pages.yml`.

CI discipline is good for a project this age. **No coverage threshold is
enforced** — `pytest --cov` reports but does not gate (`backend-ci.yml:74`).

### Gaps

- No load or performance test.
- No contract test against Razorpay's sandbox.
- Frontend component testing is effectively absent, which matters because
  **entitlement enforcement currently lives entirely in a React component**
  (§4).

---

## 9. Overall read

The infrastructure and security engineering are stronger than the product
surface. RLS with FORCE + a boot-time role assertion, replay-protected webhooks,
fail-closed RBAC with DB re-check, and a partition maintenance job are all
things most seed-stage codebases don't have.

The billing layer has clearly been hardened twice (`PAYMENT_AUDIT.md`,
`PAYMENT_REVIEW_ROUND2.md`) and the source now handles the hard parts — payment
capture verification, amount matching, event ordering, post-commit
notifications — correctly. What it lacks is **breadth**: no plan changes, no
invoices, no dunning, no server-side entitlement.

For Phase 4, the honest starting position is that this product is **configurable
in name only**. Five verticals are five sets of hardcoded Python modules plus a
four-field profile row. The customization layer has to be built, not extended.
