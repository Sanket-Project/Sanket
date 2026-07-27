# 04 — Phase 5 Verification

**Date:** 2026-07-26 (later same day)
**Mode:** verification only. No application code written, nothing committed.
**Environment:** `localhost:5173` → Vite proxy → `127.0.0.1:8000`, driven via Chrome.
**Razorpay:** keys still blank (`/billing/config` → `{"configured":false}`). No live
payment matrix.

---

## Headline

Two of the five P0s were **overstated in `02` and are corrected below.** One is
**broader** than reported. Two are confirmed unchanged. Tenant isolation was
tested live for the first time and **holds against five attack classes.** The
`/billing/plans` 500 has been narrowed from "unknown" to a single fault line with
one leading hypothesis and exact confirmation steps.

The running build has not changed: `openapi.json` still reports 91 paths, no
`/billing/subscription/verify`, and `trial_days` still caller-supplied with
`maximum: 60`. `HEAD` is still `65023e1`.

---

## Scorecard

| ID | Finding | Verdict | Change |
|---|---|---|---|
| P0-1 | No server-side entitlement | **CONFIRMED** | none |
| P0-2 | `/billing/plans` 500 | **CONFIRMED + root-caused** | fault line isolated |
| P0-3 | Onboarding completion not persisted | **CHANGED** | severity down; root cause now exact |
| P0-4 | Industry selection never applied | **CHANGED** | was overstated; scoped to first session |
| P0-5 | Password echoed in 422 body | **CONFIRMED + BROADER** | affects login too, not just signup |
| — | Live cross-tenant isolation | **PASS** | newly tested |
| NEW-1 | Industry access ungated across all five verticals | **NEW** | P1 |
| NEW-2 | `/financial/impact` ignores the industry horizon | **NEW** | P2 |

---

## P0-1 — No server-side entitlement · CONFIRMED [LIVE]

Tenant `qa-alpha` (`53c83b38-…`), `GET /api/v1/billing/subscription` → `200 null`.
No subscription row exists. With that state:

```
200  /products              200  /alerts
200  /skus                  200  /webhooks/endpoints
200  /inventory/levels      200  /financial/impact
200  /signals               200  /billing/usage
```

Unauthenticated control, same endpoints: **401**. So authentication works
correctly and it is specifically *entitlement* that is absent. Unchanged from
`02`. Still the most commercially serious finding in the audit.

---

## P0-2 — `/billing/plans` 500 · CONFIRMED, fault line isolated [LIVE]

### What I established

`/billing/usage` returns **200 for a tenant with no subscription** and **500 for a
tenant that has one**. That is the discriminator, and it is decisive.

| Tenant | Has subscription | `/billing/subscription` | `/billing/usage` | `/billing/plans` |
|---|---|---|---|---|
| `qa-alpha` | no | 200 `null` | **200** | **500** |
| `sanket-dev` | yes (`enterprise_monthly`) | 200 | **500** | **500** |

`GET /billing/usage` only calls `session.get(Plan, sub.plan_id)` when a
subscription exists (`billing.py:300` in the working tree; the same shape at
`HEAD:billing.py:175`). When there is no subscription it never touches the table
and returns 200.

**Conclusion: every code path that reads the `plans` table returns 500. No other
billing path fails.** `/billing/config` (no DB) → 200. `/billing/subscription`
(reads `subscriptions` only) → 200.

Both 500 responses carry **no `X-Request-ID` header**, although
`TenantContextMiddleware` sets it on every response it handles
(`tenant_context.py:154`). With `BaseHTTPMiddleware`, an exception raised inside
`call_next` skips the post-processing that adds the header, so the response is
coming from Starlette's outermost error handler. Consistent with an unhandled
exception, not a caught one.

### Leading hypothesis **[ASSUMPTION — needs the traceback to confirm]**

The database is behind the migration chain, and the `plans` table lacks a column
the running `Plan` model selects.

`HEAD`'s `Plan` model maps `razorpay_plan_id`
(`git show HEAD:backend/app/models/billing.py`). Migration
`0010_stripe_to_razorpay.py:44` renames `plans.stripe_price_id` →
`razorpay_plan_id`. If `0010` has not been applied, the column the ORM selects
does not exist and asyncpg raises `UndefinedColumnError` on every `SELECT` —
which matches the observed behaviour exactly, including that it is a *read*
failure on one table only.

Supporting: `Database.check_migration_version` (`database.py:177-214`) only
**logs a warning** when the DB is behind (`database.migration_check.behind`) and
never blocks startup, so this can persist silently.

Competing hypothesis, weaker: a `NOT NULL`-mapped column
(`included_quotas`, `overage_rates_cents`, `is_active`) contains `NULL` in some
row. Weaker because it would require a hand-edited row.

### Exact commands to confirm — 60 seconds

Run these and paste the output. This is the single highest-value action available.

```bash
# 1. The traceback. Grep the backend terminal / container log for the failing request.
docker compose logs backend --tail=200 | grep -A 40 -i "traceback\|billing.plans\|UndefinedColumn"

# 2. Is the DB behind? This warning is logged at every boot.
docker compose logs backend | grep "migration_check"

# 3. Ground truth on the schema.
docker compose exec postgres psql -U sanket_app -d sanket -c "\d plans"
docker compose exec postgres psql -U sanket_app -d sanket -c "SELECT version_num FROM alembic_version;"
docker compose exec postgres psql -U sanket_app -d sanket -c "SELECT id, base_price_cents, razorpay_plan_id, is_active FROM plans;"
```

If `\d plans` shows `stripe_price_id` rather than `razorpay_plan_id`, the
hypothesis is confirmed and the fix is `alembic upgrade head`.

---

## P0-3 — Onboarding completion not persisted · CHANGED [LIVE + SOURCE]

**`02` said the tenant is trapped "forever". That was wrong. Correcting it.**

Logging out and back in resolves it. After a fresh login as `qa-alpha`:

```
URL after sign-in            : /workspace     (not bounced to /onboarding)
session.onboarding.status    : complete
GET /api/v1/onboarding/state : {"status":"complete","current_step":"done"}
```

### The precise root cause, which is narrower and more useful

`sanket.dev.session` is written to localStorage at exactly **two** places, both
login/signup paths: `stores/auth.ts:206` and `:242`. The onboarding wizard calls
`setOnboarding(next)` (`OnboardingPage.tsx:109` → `stores/auth.ts:110`), which
does `set({ onboarding: o })` — **an in-memory Zustand update only.** Nothing
rewrites the persisted blob.

On boot, `stores/auth.ts:159-160` rehydrates from that stale localStorage value.

So the behaviour is:

| Navigation type | Result |
|---|---|
| SPA-internal routing (clicking links) | works — in-memory store is current |
| **Full page load** (F5, typed URL, new tab, bookmark) | rehydrates stale `in_progress` → `OnboardingGate.tsx:12` bounces to `/onboarding` |
| Log out and back in | fixed — the blob is rewritten |

**Revised severity: still P0.** Not because it is permanent, but because a user
reloading the page immediately after finishing setup is an ordinary action, and
the recovery (log out, log back in) is not discoverable. My original repro was
correct; my inference of permanence was not.

**Fix shape:** have `setOnboarding` also write `localStorage[DEV_SESSION_KEY]`, or
rehydrate the slice from `GET /onboarding/state` on bootstrap rather than trusting
the snapshot.

---

## P0-4 — Industry selection never applied · CHANGED [LIVE]

**`02` said the industry is "never applied" and that a pharma tenant is
"permanently" served fashion. Also wrong, and this is the more important
correction of the two.**

After re-login, the archetype resolves correctly:

```
JWT claim                 : ind = pharma
GET /industry/profile     : {"code":"pharma","display_name":"Pharmaceuticals",
                             "effective_horizon":52,
                             "active_signal_types":["regulatory","macro_economic",
                                                    "logistics_disruption",...]}
GET /industry/context     : {"code":"pharma","default_horizon_weeks":52,
                             "granularity_dimensions":["ndc","channel","region","cold_chain"]}
GET /inventory/levels     : {"industry":"pharma",...}
```

Horizon 52, pharma signals, pharma granularity dimensions. All correct.

### What is actually wrong

The JWT is minted at login with `ind` read from the DB. Choosing an industry
during onboarding updates the DB but **does not re-mint the token**, and the
token lives ~1h (`exp - iat = 3600`). So for the remainder of the session in
which the tenant completes onboarding, every API call carries `ind: "fashion"`
(the signup default) while the UI chrome renders the chosen industry.

**Revised severity: P1, not P0.** It is bounded by one session and one token
lifetime.

**But the compliance concern in `03` stands, in narrowed form.** During that first
session a pharma tenant is served the fashion archetype and **standard audit
level** while the header displays `GXP · 21 CFR PART 11`. The first session is
exactly when a new tenant runs their baseline forecast. A window is smaller than
a permanent state, but for a validated-systems buyer a window in which the audit
level silently differs from the badge is still a finding. It should be fixed
before selling into pharma, and `03`'s "do not sell into pharma until this is
fixed" guidance is unchanged.

Same root cause family as P0-3: session state established at login and never
refreshed mid-session.

---

## P0-5 — Password echoed in 422 body · CONFIRMED and BROADER [LIVE]

`02` scoped this to signup. It is **the global FastAPI validation handler**, so it
affects every endpoint that accepts a password.

```
POST /api/v1/auth/signup    {"email":"…","password":"SuperSecret!456"}
 → 422  "input":{"email":"leak-probe2@example.com","password":"SuperSecret!456"}
        password echoed: true

POST /api/v1/auth/dev-login {"password":"LoginSecret!789"}
 → 422  "input":{"password":"LoginSecret!789"}
        password echoed: true
```

Both leak. By extension so will `/auth/reset-password` and any future
credential-taking endpoint. **Severity raised**: this is a platform-wide
credential disclosure into the browser, and from there into any error-tracking
SDK, proxy log, or CDN log. Still fixable with a single custom
`RequestValidationError` handler in `app/main.py` that strips or redacts `input`.

---

## Live cross-tenant isolation · PASS [LIVE]

Previously blocked by P1-9. Worked around by using `POST /auth/dev-login`, which
returns a functioning token where the signup response's `access_token` does not.

**Tenant A** = `qa-alpha` (`53c83b38-…`, pharma).
**Tenant B** = `sanket-dev` (`f8f286bd-…`, fashion, holds an active
`enterprise_monthly` subscription).

| # | Attack | Result |
|---|---|---|
| 1 | A sends `X-Tenant-Id`, `X-Tenant`, `Tenant-Id`, `X-Tenant-ID` = B's UUID | 200, but A still sees **its own** empty state. B's subscription id never leaked |
| 2 | A reads B's product by direct UUID (`GET /products/{B_uuid}`) | **404** — and 404, not 403, so existence is not confirmed |
| 3 | A sends `DELETE` and `PATCH` on B's product | **404** both |
| 4 | A's list view after B creates a product | `[]` — no leakage |
| 5 | A forges its JWT: `tid` swapped to B, original signature retained | **401** |
| 6 | A sends `alg:none` with an unsigned payload | **401** |
| 7 | Control: B reads its own product | 200 |

Method: B created a product `ZZ-ISOLATION-PROBE`
(`073fc270-2902-477e-9533-bc612ed74b18`), A attempted read/modify/delete, then B
deleted it. **Cleanup confirmed — `DELETE` returned 200. No probe data remains in
your database.**

**Verdict: tenant isolation holds under live attack**, matching what static
analysis predicted in `01`. RLS with `FORCE ROW LEVEL SECURITY`, the absence of
any caller-supplied `tenant_id`, and JWT signature verification are all doing
their jobs. This is the strongest part of the system and it is now empirically
confirmed, not assumed.

---

## NEW-1 — Industry access is ungated across all five verticals · P1 [LIVE]

Not a security defect. A monetization defect.

```
A sets X-Industry-Code: fashion      → 200, served fashion
                        electronics  → 200, served electronics
                        agrocenter   → 200, served agrocenter
                        hardware     → 200, served hardware
                        pharma       → 200, served pharma
                        NOT_A_REAL   → 400 "Unknown industry code"
```

Validation is correct and rejects garbage. But every tenant's JWT carries
`industries: ["fashion","electronics","pharma","agrocenter","hardware"]` — all
five, for everyone (seeded at `database.py:283`, and the deny-by-default check at
`tenant_context.py:114-138` therefore never denies).

Combined with P0-1, a tenant **with no subscription at all** has working access to
every vertical the product sells. If verticals are ever priced separately, or if
GxP is ever a paid tier, this is the gate that has to exist. Worth deciding now,
because it interacts directly with the customization strategy's per-vertical
billing model (`customization-plan.md` §A.8).

---

## NEW-2 — `/financial/impact` ignores the tenant's forecast horizon · P2 [SOURCE]

`app/routers/financial.py:26` declares `horizon_weeks: int = 12` as a query-param
default. For the pharma tenant, whose `effective_horizon` is 52
(`/industry/profile`, verified live), the endpoint returned
`{"industry":"pharma","horizon_weeks":12,...}`.

Same defect class as `StepCalendar.tsx:53` hardcoding 13 (P1-7 in `02`): a
per-industry value exists and is resolved correctly, and then a hardcoded literal
overrides it at the point of use. Worth a sweep for other hardcoded horizons
before the customization work starts, since the whole premise of that work is
that resolved config actually reaches the code that uses it.

---

## Review of the uncommitted payment workstream

Requested in Step 0. **Reviewed, not committed.**

### Scope

Larger than the 462 lines in two files. The full uncommitted surface:

| Modified (backend) | Lines |
|---|---|
| `app/services/billing/subscription_manager.py` | +369 |
| `app/services/integrations/file_import.py` | +318 |
| `tests/test_file_import.py` | +225 |
| `app/routers/billing.py` | +122 |
| `app/services/billing/razorpay_client.py` | +112 |
| `tests/test_rate_limit.py` | +75 |
| `app/routers/integrations_hub.py` | +49 |
| `app/config.py` | +21 |
| `.env.example` | +9 |
| `app/models/billing.py`, `product.py`, `tenant.py`, `services/billing/__init__.py` | small |

**Backend total: 1,235 insertions, 90 deletions across 13 files.** Plus 10
modified frontend files, plus untracked:

- `backend/alembic/versions/0017_billing_p0_guards.py` (79 lines) — adds
  `plans.trial_days`, backfills it to 14 for priced plans, creates
  `uq_subscriptions_one_live_per_tenant`. Revision chain is clean: `0017` →
  `down_revision 0016`, linear, no branch.
- `backend/tests/test_billing.py` (647 lines) — the billing test suite.
- `backend/scripts/sync_razorpay_plans.py` — referenced by
  `subscription_manager.py:138`'s error hint. Without it the misconfiguration
  guard tells operators to run a script that is not in the repo.
- `backend/sql/013_sandbox_user.sql` (58 lines) — the sandbox-CTA fix from review
  round 2.
- `frontend/src/utils/razorpay.ts` (77 lines) — imported by
  `SubscriptionGate.tsx:13`.
- `PAYMENT_AUDIT.md`, `PAYMENT_REVIEW_ROUND2.md` — both prior reviews.

### Safety assessment

- **Secrets: clean.** No `rzp_live`, `sk_live`, private keys, or long literal
  tokens in either the tracked-file diff or the untracked files.
- **Debug leftovers: clean.** No `console.log`, `print(`, `breakpoint`, or
  `pdb.set_trace` in added lines.
- **`.env.example` additions are documentation only** — `APP_BASE_URL` plus a
  comment pointing at `sync_razorpay_plans`. No real values.
- **`config.py` addition is sound.** `billing_callback_base` derives the payment
  callback origin from server config with a fallback chain, never from the request
  body. That is the correct fix for the callback-hijack hole and the comment
  explains why.
- **Migration `0017` is well-formed** and has a real `downgrade()`.

### Caveats before you commit

1. **This is not one change.** It bundles the payment hardening with a substantial
   `file_import` rework (+318) and an `integrations_hub` change (+49) that nobody
   in this audit has reviewed. Commit them separately so the payment fix is
   revertable on its own.
2. **The untracked files are not optional.** Committing `subscription_manager.py`
   without `0017_billing_p0_guards.py` ships code that reads `Plan.trial_days`
   against a database that has no such column — which may be exactly the class of
   failure already producing P0-2. Migration, code, and tests must land together.
3. **CRLF/LF churn.** `git diff` emits `warning: CRLF will be replaced by LF` for
   many files. Check `.gitattributes` before committing so line-ending noise does
   not swamp the real diff.
4. **`qa_artifacts/`** is untracked and contains `.xlsx`, `.json`, and `.py` test
   scratch. Decide whether it belongs in the repo or in `.gitignore`.
5. **I have not reviewed the 10 modified frontend files** beyond
   `SubscriptionGate.tsx`. Someone should.

**Recommendation:** three commits — (a) payment hardening: `billing.py`,
`subscription_manager.py`, `razorpay_client.py`, `billing/__init__.py`,
`models/billing.py`, `config.py`, `.env.example`, `0017`, `test_billing.py`,
`scripts/`, `013_sandbox_user.sql`, `razorpay.ts`, `SubscriptionGate.tsx`;
(b) file-import rework plus its tests; (c) everything else, after review.

---

## 5D — The unassessed surface

Named explicitly so silence is not read as approval. **Nothing below was assessed
this session**; each entry is a risk read and a recommendation.

### ML stack (`backend/ml/`) — assess LATER

The largest unexamined body of code in the repo and the thing the product's entire
value claim rests on. If the forecasts are not better than a naive seasonal
baseline, no amount of billing or customization work matters. The mitigating
factor is that `forecast_accuracy_metrics` and a backtest migration
(`012_forecast_accuracy_backtest.sql`) exist, so the team has at least built the
measurement apparatus.
**Trigger to assess now:** a customer asks for accuracy numbers, or you are about
to make an accuracy claim in marketing. Either makes this the top priority.

### Performance and load — assess LATER

No load test exists anywhere in the repo. The known risk concentrations are
`historical_sales` and `forecast_results` (quarterly partitions) and the planned
GIN indexes on `custom_fields`. With no paying tenants there is no production
load to be wrong about yet.
**Trigger:** before the first tenant with >50k SKUs, or before the customization
plan's Phase 3 ships custom fields.

### WebSocket realtime layer — assess LATER

`app/realtime/` plus `connection_manager.py` broadcast subscription and alert
events. Untested under concurrency. The blast radius is bounded: a realtime
failure degrades to stale UI, and `flush_notifications`
(`subscription_manager.py:512`) already treats publish failure as non-fatal.
**Trigger:** first multi-user tenant, or any report of missed alerts.

### External signal connectors — assess NOW (this is the one I would pick)

Eleven connectors exist in `app/services/external_signals/`. Four integrations are
implemented in `app/services/integrations/`. The onboarding UI claims **"Shopify,
Amazon FBA, and 30+ sources"** and Amazon FBA does not exist
(`02`, P2-7). This is the cheapest thing on this list to check and the only one
that is currently making a false claim to prospects. It is also directly load-
bearing for the customization plan's recommendation to build Apparel first, which
rests entirely on Shopify and WooCommerce actually working.
**Recommendation:** verify Shopify and WooCommerce against a real sandbox store
before the next sales conversation, and correct the "30+ sources" copy.

### Accessibility — assess LATER, but cheap

No WCAG pass has been run. One concrete observation from this session: the login
page places `SOC 2-aligned · Role-based access · Tenant-isolated` in low-contrast
text on a dark panel. Colour contrast is also a live concern for the
customization plan's tenant-configurable accent colour (§A.13 already mandates a
contrast check).
**Trigger:** any enterprise or public-sector procurement, which will ask for a
VPAT. Also worth noting the `design:accessibility-review` skill is installed and
unused.

**I assessed none of these in depth this session** — 5A through 5C consumed the
budget, which was the right trade.

---

## Open items for you

1. **Run the four diagnostic commands in P0-2.** One traceback closes the biggest
   unknown in this audit.
2. **Confirm the commit plan** (three commits, as above) before anything lands.
3. **Decide on NEW-1:** should industry access be gated by plan?
4. Still open from `00`: GST scope, `tenants.tier` vs `subscriptions.plan_id`
   authority, connector catalogue honesty, plan-price ownership, `test_venv/`.
