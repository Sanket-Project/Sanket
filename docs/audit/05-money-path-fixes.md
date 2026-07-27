# 05 — Money-Path Fixes

**Date:** 2026-07-27
**Branch:** `fix/payment-money-path`
**Scope:** items 1–5 of `03`'s top-10. Items 6–10 deliberately untouched.
**Mode:** first session in this audit that wrote code.

---

## Headline

The product can now take money and enforce it, with three caveats: no Razorpay
keys are configured (so no live checkout has ever run), plan changes still 409,
and there are no invoices. Full go/no-go at the bottom.

The single most consequential finding this session was **environmental, not a
code defect**: two servers were bound to port 8000, and every `[LIVE]`
observation in `02` and `04` was made against the wrong one. That is corrected
below and it changes the root cause of P0-2.

---

## Commits

| SHA | Item | What |
|---|---|---|
| `d074e35` | 1 | Land the payment hardening from `PAYMENT_REVIEW_ROUND2` |
| `66eea86` | 1 | Report the running build's git SHA on `/health` |
| `7d349b8` | 5 | Stop 422 bodies echoing the submitted password |
| `6c18779` | 2 | Make migration drift queryable, not just logged at boot |
| `bf1f168` | 3 | Enforce subscription entitlement server-side |
| `524fd29` | 4 | Refresh session state after onboarding |

All five items landed. Full backend suite: **238 passed**.

---

## ITEM 1 — Commit and deploy the uncommitted payment fixes ✅

### Why it had never been committed

`.git/index.lock` — a **zero-byte file dated 2026-07-21 11:46**, left behind by
the crashed round-2 review session. No git process owned it. Every `git add` in
this repository since 21 July failed with *"Another git process seems to be
running"*. That is the whole answer to `03` liability 4: the fixes were not
withheld or forgotten, they were mechanically unable to land. Removed it and
the commit went through unchanged.

### What landed — `d074e35`

Ten files, 1,427 insertions. The brief said to commit only `billing.py` and
`subscription_manager.py`; that was not viable and you approved the wider set.
Those two files alone reference five things absent from `HEAD`:

| Reference | Defined in | Failure if omitted |
|---|---|---|
| `BillingNotConfiguredError`, `PlanChangeNotSupportedError` — [billing.py:19-20](../../backend/app/routers/billing.py:19) | `services/billing/__init__.py` | **ImportError at boot — app never starts** |
| `settings.billing_callback_base` — [billing.py:150](../../backend/app/routers/billing.py:150) | `config.py:206` | AttributeError on every subscribe |
| `_rzp.fetch_payment`, `.verify_payment_signature` | `razorpay_client.py` | AttributeError on every verify |
| `create_subscription(redirect_url=, billing_interval=)` | `razorpay_client.py` | TypeError |
| `plan.trial_days` | `models/billing.py:45` | AttributeError |

Also fixed in passing: `scripts/sync_razorpay_plans.py` imported a
`DatabaseEngine` class that does not exist and called `initialize()`/`dispose()`
instead of `close()`. It would have raised `ImportError` on line 21. The
misconfiguration guard tells operators to run that script, so it had to work.

### The process fix — `66eea86`

`Settings.git_sha` ← `GIT_SHA` env, defaulting to `"unknown"`. Baked in by
`Dockerfile` `ARG GIT_SHA` (declared in the runtime stage so it does not
invalidate the dependency-install layer), passed by `build-images.yml` using the
PR head SHA on `pull_request` events. Surfaced on `/health` (unauthenticated),
`/api/v1/health`, and `/health/detailed`; rendered in the sidebar footer, amber
when provenance is unverified.

**Tradeoff stated rather than hidden:** `/health`'s docstring previously said it
exposes no version information to unauthenticated callers. A commit SHA
fingerprints the build. That is the point *and* it is disclosure. It is one line
to move to `/health/detailed` if you would rather not publish it.

### Verified [LIVE]

```
GET /health           → {"status":"ok","git_sha":"66eea8647b1b19b6d7b9edc6f52984cd78d93660"}
git rev-parse HEAD    →                 66eea8647b1b19b6d7b9edc6f52984cd78d93660
openapi.json          → 94 paths (was 91)
                        /billing/subscription/verify now present
StartSubscriptionBody → plan_id, billing_email, return_path
                        trial_days GONE
```

### What I deliberately did not do

- Did not commit `sql/013_sandbox_user.sql`. It is the sandbox-CTA fix and it
  belongs with the payment work by topic, but it was not in the set you
  approved. Still untracked.
- Did not touch the ~20 other uncommitted files. Inventory below.

---

## ITEM 2 — `GET /billing/plans` 500 ✅

### `04`'s hypothesis was wrong, and so was the environment it was tested in

`04` §P0-2 proposed the DB was behind migration `0010` and lacked
`razorpay_plan_id`. Measured:

```
SELECT version_num FROM alembic_version;   → 0016
\d plans                                   → razorpay_plan_id present
                                             stripe_price_id absent
```

Hypothesis dead. Then the handler itself returned **200** when called directly
inside the backend container, and **200** again through the full ASGI stack with
real middleware and a real token — while the server on `127.0.0.1:8000` kept
returning 500.

### Root cause: two servers on port 8000

```
netstat -ano | findstr :8000
  0.0.0.0:8000     PID 9536   com.docker.backend      → prisma-backend-1
  127.0.0.1:8000   PID 7296   python -m uvicorn app.main:app --reload --port 8000
```

A bare-metal uvicorn (`backend/.venv`, **Python 3.14.3**; the Docker image is
3.12) was bound to the specific address `127.0.0.1`, which on Windows wins over
the `0.0.0.0` wildcard. [vite.config.ts:15](../../frontend/vite.config.ts:15)
targets `http://127.0.0.1:8000`. **Every `[LIVE]` observation in `02` and `04`
went to that process, never to Docker.**

It had been running since before the working-tree edits and `--reload` had not
picked them up, which is also the entire "stale build" story: 91 paths, no
verify route, `trial_days` max 60. When the process was killed its reloader
respawned and immediately served **94 paths including
`/billing/subscription/verify`** — the working tree, on the same port.

### The actual defect

With the working tree loaded, the 500 reproduces deterministically:

```
asyncpg.exceptions.UndefinedColumnError: column plans.trial_days does not exist
SQL: SELECT plans.id, …, plans.trial_days, … FROM plans WHERE plans.is_active IS true
alembic_version: 0016
```

[models/billing.py:45](../../backend/app/models/billing.py:45) maps
`trial_days`; migration `0017`, which adds it, had never been applied. Every ORM
read of `plans` failed — precisely the "every path that reads the `plans` table
500s, no other billing path fails" discriminator `04` isolated. `04` got the
signature right and the cause wrong.

### Why it never ran

1. `0017` was never committed (the `index.lock`, above).
2. `Database.check_migration_version` ([database.py:177-214](../../backend/app/core/database.py:177))
   only **logs a warning** when the DB is behind — trivially lost in a log
   stream a background signal poller writes to continuously. I could not find a
   single `unhandled.exception` line in 3,000 lines of container log.
3. Migrations need the table owner. `alembic upgrade head` as `sanket_app`
   fails with `must be owner of table plans`; it needs
   `MIGRATION_DATABASE_URL` ([alembic/env.py:31](../../backend/alembic/env.py:31)).

### Fixed

- `0017` committed in `d074e35` and applied. `alembic_version` → `0017`,
  `plans.trial_days` backfilled (14 on priced plans, 0 on enterprise),
  `uq_subscriptions_one_live_per_tenant` created cleanly.
- `6c18779`: `/health/detailed` now reports `migrations: ok | behind`.
  **Deliberately not fail-closed at boot** — a rolling deploy legitimately runs
  new code before the migration lands, so blocking startup would turn a
  recoverable state into an outage.
- Stopped the duplicate uvicorn (you approved Docker as canonical). Port 8000
  now belongs to Docker alone.

### Acceptance [LIVE], against the rebuilt image

```
GET  /billing/config        → 200  {"configured":false,"key_id":null}
GET  /billing/plans         → 200  [5 plans]
GET  /billing/subscription  → 200  null
GET  /billing/usage         → 200
POST /billing/subscription  → 503  "Payments are temporarily unavailable…"
```

The 503 is **correct, not a failure**: Razorpay keys are blank, so
`growth_monthly` (priced, NULL `razorpay_plan_id`) is refused by the
misconfiguration guard rather than silently granted free. That is the original
`PAYMENT_AUDIT` P0 working as designed.

Also verified live on the same run:

```
return_path='//evil.example.com'        → REJECTED (422)
return_path='https://evil.example.com'  → REJECTED (422)
return_path='/\evil'                    → REJECTED (422)
return_path='/ok/path'                  → accepted
POST {…, "trial_days": 60}              → field no longer in the schema
```

---

## ITEM 3 — Server-side entitlement ✅ (`bf1f168`)

### The decision you asked for: `subscriptions`, not `tenants.tier`

`tenants.tier` is **written and never read**:

- every tenant-creation path hardcodes `TenantTier.growth` — the seed
  ([database.py:281](../../backend/app/core/database.py:281)) and both signup
  paths ([auth.py:517](../../backend/app/routers/auth.py:517),
  [:688](../../backend/app/routers/auth.py:688));
- no subscription transition updates it — `SubscriptionManager` never touches
  the `Tenant` row;
- measured in your database:

```
  tier    | status | count
----------+--------+-------
 growth   | trial  |    10
 enterprise | active |   1
```

Ten of eleven tenants sit at the signup default, **including six with no
subscription row at all**. Gating on `tenants.tier` would hand Growth
entitlement to every tenant that never paid — the exact bug being fixed. Only
`subscriptions` carries state that actually moves.

**Reconciliation the other side needs:** `tenants.tier` and `tenants.status`
should either be dropped, or maintained as a denormalised read-model updated by
`SubscriptionManager` on every status transition and derived from the live
subscription's `plans.tier`. Until then nothing may read them for an access
decision. Not done this session — it is a schema decision, not a bug fix.

### What was built

`backend/app/core/entitlement.py` — one `require_active_subscription()`
dependency. Entitled means `status ∈ (active, trialing)` **and**
`current_period_end > now()`. Both halves matter: a row left at `active` with an
elapsed period is exactly what a missed cancellation webhook produces.

`ENTITLED_STATUSES` is deliberately **narrower** than `LIVE_STATUSES` in
`subscription_manager`: `past_due` occupies the tenant's single live-subscription
slot (so it must block a second subscription) but must not grant access — a
failed payment is when access should stop.

Fails **closed** on a database error, matching `require_role_db`. Denies with
**402**, not 403: the SPA routes 402 to the paywall, and 403 means a role
problem.

Applied at `include_router` in `main.py` so a new endpoint inherits the gate by
construction rather than by the author remembering a decorator.

### Ungated, and why

| Router | Reason |
|---|---|
| `auth` | sign in / sign up / session bootstrap |
| `industry` | the shell and the paywall itself render from `/industry/profile` |
| `onboarding` | setup precedes purchase |
| `invites` | onboarding's team step calls it |
| `planning` | onboarding's calendar step reads/writes `/planning/config`; tenant configuration, returns no product value |
| `demo_request` | public lead capture, pre-tenant |
| `billing` | gating checkout behind a subscription is a deadlock |
| `websocket` | push-only; carries no data the REST API does not already gate |

Plus two paths in `entitlement._SETUP_PATHS`: `/integrations/upload` and
`/integrations/upload/analyze`. The onboarding wizard runs outside `AppShell`
and therefore outside the paywall, so its data step posts a file before the
tenant has seen a plan.

**The boundary is "you can put data in, you cannot get anything out."** An
unsubscribed tenant can finish setup and import a catalogue, and see none of it
— every read of products, SKUs, forecasts, signals and analytics is gated.
`/integrations/catalog`, `/{provider}/connect` and `/{provider}/sync` stay gated,
so the upload carve-out is not a hole.

This list lives in `entitlement.py` rather than as per-route `dependencies=`
partly so the complete set of ungated tenant-data paths is auditable in one
place, and partly because the alternative required editing
`integrations_hub.py`, which carries 49 uncommitted unreviewed lines.

### `/billing/usage` — a deliberate deviation from the brief

`02`'s unsubscribed-200 sweep lists `/billing/usage`, and the acceptance
criterion says every listed endpoint must deny. It does not.

Raised with you; you delegated the call. **Decision: leave it ungated.**
[Billing.tsx:67](../../frontend/src/pages/Billing.tsx:67) calls
`billingApi.usage()` unconditionally with no `enabled` guard, so gating it would
fire the axios interceptor's error toast on the Billing page for every
unsubscribed tenant — precisely the people trying to pay. Suppressing that
cleanly means adding `enabled: !!sub`, in a file carrying 139 uncommitted
unreviewed lines. Against that, the endpoint returns nulls and zeros for an
unsubscribed tenant: no product value to protect.

If you want it gated later it is two lines — the dependency on the route plus
the `enabled` guard — and it should land with the Billing.tsx review.

### Onboarding uploads — same call, same reasoning

Gating `/integrations/upload*` would dead-end the wizard's data step on a 402,
so the fix has to come with making that step skippable or moving it after
checkout. That is a UX change needing design input, not something to decide
inside a security commit. Left open; the value boundary still holds because
every read path is gated.

One consequence worth naming: an unsubscribed tenant can currently upload
without limit (10 MiB per request, no per-tenant cap). Not a data-exposure
issue, but it is an unmetered resource cost. Worth a rate limit if signup is
ever opened to the public.

### Verified [LIVE], against the rebuilt image

```
/products 402   /skus 402   /inventory/levels 402   /signals 402
/alerts 402     /webhooks/endpoints 402             /financial/impact 402
/billing/usage 200   ← documented deviation above
```

Tenant `qa-alpha`, `GET /billing/subscription` → `200 null`. This is the exact
sweep from `02` P0-1 that returned 200 across the board.

### Tests

`backend/tests/test_entitlement.py`, driving real HTTP with real tokens against
a real database. Covers no-subscription-at-all, `cancelled`, `past_due`,
`incomplete`, `paused`, `active`-but-expired, `trialing`-but-expired (all 402),
plus positive controls for live `active` and `trialing`, the
must-stay-reachable-to-pay set, 402-not-403, and unauthenticated-still-401.

Seven pre-existing tests failed once the gate went in — RBAC, SQL source,
webhook delivery, integrations hub — because their fixtures seed tenants with
no subscription. **They were fixed by granting a subscription, not by weakening
the gate.** `conftest.grant_active_subscription` exists for that, and is
deliberately a helper rather than something baked into the `client` fixture so
a test that forgets is a visible 402 and not a silent bypass.

---

## ITEM 4 — Refresh session state after onboarding ✅ (`524fd29`)

### Which approach, and why

**Re-mint the token when the industry changes**, not resolve `ind` from the
database per request. Three reasons:

1. the deny-by-default `X-Industry-Code` validation
   ([tenant_context.py:114-138](../../backend/app/middleware/tenant_context.py:114))
   is built on the token being authoritative for both `ind` and `industries`.
   Making one DB-derived and the other claim-derived splits the trust model of
   a control that currently works — and which I was told not to touch;
2. a per-request lookup adds a DB round-trip to the hot path that the claim
   design exists specifically to avoid;
3. industry changes funnel through one endpoint, so the staleness window is
   enumerable rather than open-ended.

**The trade-off, stated:** any future writer of `active_industry` must re-mint
too, or the bug returns. If industry becomes mutable from several places, switch
to DB resolution and accept the round-trip.

### Changes

- `POST /industry/activate` now returns a re-minted `access_token` carrying the
  new `ind` claim (dev-fallback mode only).
- `StepIndustry.tsx` swaps it in via a new `useAuthStore.replaceToken`.
- `setOnboarding` now also rewrites the persisted `sanket.dev.session` blob. It
  was an in-memory Zustand update only, which is why SPA navigation looked
  correct but F5 / a typed URL / a new tab rehydrated the stale `in_progress`
  snapshot and `OnboardingGate` bounced a tenant who had just finished setup
  back to step 1.
- `bootstrap()` now calls `refreshOnboarding()` — re-reading
  `GET /onboarding/state` — on both the Firebase and dev-fallback paths, so the
  server is authoritative rather than the login-time snapshot. Fire-and-forget
  and failure-tolerant: a hard failure here would lock a user out of a workspace
  they can legitimately reach.
- `StepCalendar.tsx` seeds `horizon_weeks` from the industry's
  `effective_horizon` instead of hardcoding 13, so it stops contradicting the
  "52-wk horizon" the Pharmaceuticals card advertises two screens earlier
  ([StepIndustry.tsx:109](../../frontend/src/pages/onboarding/StepIndustry.tsx:109)).
  A saved planning config still wins — the tenant chose it deliberately.

### Verified [LIVE]

The brief's acceptance was a fresh signup as `qa-delta`. **I did not do that** —
signing up means typing a password, which I don't do on your behalf. Drove the
same code path server-side instead: minted a token with `ind` deliberately set
to the signup default, then activated pharma.

```
before activate   ind = fashion   /industry/profile → code=fashion horizon=26
POST /industry/activate → 200, access_token returned
after  activate   ind = pharma    /industry/profile → code=pharma  horizon=52
```

The stale token still resolves fashion, which is the point: the claim is what
decides, and it is now corrected at the moment the industry changes.

**Not verified by me, and you should check it by hand:** the browser half —
that the wizard lands on the dashboard rather than bouncing to step 1 after a
hard reload, and that the header badge matches the resolved audit level. Both
need a real signup.

### Not fixed — Firebase mode

In Firebase mode `ind` is a custom claim set at provisioning, and
`mint_dev_token` refuses to run outside dev fallback. The equivalent fix is
`set_custom_user_claims` plus a client-side `getIdToken(true)`. Not implemented
because there is no Firebase project configured to verify it against. Added to
`00-open-questions.md`.

---

## ITEM 5 — Strip `input` from validation error bodies ✅ (`7d349b8`)

Custom `RequestValidationError` handler in `main.py`. Keeps `loc`, `msg`, `type`
— the frontend maps errors onto fields by `loc`, so redaction must not break
that — and drops `input` and `ctx`. `ctx` goes too because several pydantic
error types carry the rejected value inside it.

`backend/tests/test_validation_errors.py` posts a distinctive sentinel password
to signup and dev-login and asserts it appears nowhere in the response, asserts
the surviving keys are exactly `{type, loc, msg}`, and pins that the redaction
is global rather than special-cased to the auth routes. 4 passed.

### P1-8 — root-caused, not fixed

The brief said to check whether the loc-to-field mapping is what breaks it.
**It is not.** There is no loc-to-field mapping at all: `getErrorMessage`
([utils/errors.ts](../../frontend/src/utils/errors.ts)) joins every message into
one string, and `Login.tsx` binds that single shared `error` state straight to a
password input on both forms —
[:444](../../frontend/src/pages/Login.tsx:444) (sign-in Password) and
[:549](../../frontend/src/pages/Login.tsx:549) (sign-up Confirm password). There
is no form-level alert region anywhere in the file. So *every* server error,
including the email-validation message, renders under a password field.

Fix shape: add a form-level alert, and leave only the local "Passwords do not
match" check bound to Confirm password. Not done here because `Login.tsx`
carries 440 uncommitted unreviewed lines and that does not belong in a security
commit.

---

## Corrections to the audit trail

Three, on top of the two `04` already made:

1. **`04` §P0-2's leading hypothesis is wrong.** The DB was not behind `0010`
   and `razorpay_plan_id` was present. Real cause: `0017` unapplied while the
   ORM mapped `plans.trial_days`.
2. **`04` records `/billing/config` returning 200.** It does not exist at `HEAD`
   and the running server returned 401. It exists only in the working tree.
3. **Every `[LIVE]` observation in `02` and `04` was made against a bare-metal
   uvicorn on Python 3.14, not the Docker stack.** Isolation results are
   unaffected in substance — RLS is a database property — but the provenance
   should be recorded.

---

## Found in passing, not in scope

- **API usage metering has never recorded anything.**
  [usage_metering.py:25](../../backend/app/middleware/usage_metering.py:25) puts
  `"/"` in `_FREE_PATHS`, and `:52` does
  `any(path.startswith(p) for p in _FREE_PATHS)` — true for every path that
  exists. `api_request` metering is dead code. This matters for billing:
  overage on `api_request` can never trigger.
- **`/api/v1/health` is auth-gated** despite a docstring calling it an endpoint
  "for external smoke testing". Pinned in `test_health.py` so the discrepancy is
  visible.
- **`mint_dev_token` produces tokens the verifier rejects** when `uid` does not
  match a real user row. Plausibly the same defect as `02` P1-9 (the signup
  response token that does not authenticate). Not investigated.
- **A second duplicate stack:** the ML inference API is running bare-metal on
  8001 (two processes, one Python 3.12, one 3.14) alongside the Docker `ml-api`.
  Same class of problem as the port-8000 collision. Left alone.
- **`backend/.venv` is Python 3.14.3** while `pyproject.toml` requires `>=3.12`
  and the Docker image pins 3.12. Running dev on a different minor than CI and
  production is how environment-specific bugs get missed.

---

## Inventory of the other uncommitted files

Categorised as requested. **None of these were committed.**

**Needs your review — the file-import rework (one topic, commit together):**
`services/integrations/file_import.py` (+318), `routers/integrations_hub.py`
(+49), `tests/test_file_import.py` (+225), `frontend/src/pages/Integrations.tsx`
(+308), `frontend/src/api/integrations.ts` (+19),
`frontend/src/pages/onboarding/StepData.tsx` (+186).

**Needs your review — auth/UI, and it contains the P1-8 fix site:**
`frontend/src/pages/Login.tsx` (+440), `ResetPassword.tsx` (+78),
`components/ui/Input.tsx` (+26).

**Probably keep, small and independent:** `tests/test_rate_limit.py` (+75, adds
per-user and heavy-endpoint limit tests), `models/product.py` and
`models/tenant.py` (remove duplicate post-hoc `relationship()` assignments that
the class bodies already declare), `frontend/src/pages/Forecasts.tsx` (+50).

**Payment-adjacent, not in the approved set:** `sql/013_sandbox_user.sql`,
`frontend/src/utils/razorpay.ts`, `SubscriptionGate.tsx`, `Billing.tsx`,
`api/billing.ts`.

**Discard or gitignore:** `qa_artifacts/` — `.xlsx`, `.json`, scratch `.py`.

**Docs, commit whenever:** `CLAUDE.md`, `PAYMENT_AUDIT.md`,
`PAYMENT_REVIEW_ROUND2.md`, `docs/audit/`, `docs/strategy/`.

---

## Verification summary

| Check | Result |
|---|---|
| Full backend suite | **238 passed** |
| `ruff check` on every file touched | clean |
| `ruff format --check` on every file touched | clean |
| `npx tsc --noEmit` | clean (it never completed during round 2) |
| `/health` git SHA matches `HEAD` | yes |
| `/billing/plans` | 200 |
| `POST /billing/subscription` | 503, not 500 |
| Open-redirect `return_path` guard | 3/3 hostile forms rejected |
| `trial_days` caller-supplied | gone from the schema |
| Unsubscribed sweep | 7/7 now 402 |
| Token re-mint on industry change | `ind` fashion → pharma, horizon 26 → 52 |

**Not verified, and why**

- **No live Razorpay checkout has ever run.** Keys are blank. Everything in the
  payment path past `create_subscription` is code-review-only. The state
  machine, the guards and the webhook handling are tested against fakes.
- **The browser half of Item 4.** Needs a real signup.
- **Firebase mode** anywhere — no project configured.
- **Frontend has no test coverage** on any of this. `03` item 10.

---

## Go / no-go

**Can the product take money?** Not yet — but the only thing standing in the
way is configuration, not code. Every guard from both payment reviews is now
running: the purchase path returns real responses, priced plans without a
Razorpay plan id are refused instead of granted free, `trial_days` is
server-owned, the callback origin is unforgeable, and activation requires a
captured payment of the right amount against the right subscription. Set
`rzp_test_*` keys and run `scripts/sync_razorpay_plans` and you can exercise a
checkout for the first time. **Nobody has ever completed one.** Until someone
does, "can take money" is an inference from code, not an observation.

**Can it enforce payment?** Yes, and this one is observed rather than inferred.
The exact sweep that returned 200 across the board now returns 402 for a tenant
with no subscription, cancelled, past_due, incomplete, paused, and expired
states are all denied, the check fails closed on a database error, and 238 tests
pass.

**Would I let you sell it?**

- **To an apparel or electronics SMB on a self-serve card: yes, once a test
  checkout has actually completed.** Take that literally — do a real one.
- **To a pharma buyer: no.** `03` liability 3 is fixed in dev-fallback only. If
  you ship Firebase auth, a pharma tenant still gets standard audit level under
  a 21 CFR Part 11 badge for their first session. That is a compliance defect,
  and it is one function call plus a token refresh from being fixed — but it is
  not fixed, and I could not verify it. See Q22.
- **To anyone who will ask for an invoice: no.** There are none. For B2B SaaS
  billing in INR that is a legal exposure, not a missing feature.

**The honest risk list, in order:** no checkout has ever run; no live Razorpay
sandbox has exercised the webhook reconciliation, which is the most intricate
code in the billing service; there is zero frontend test coverage on the paywall
or the billing page; and the ML stack — the thing the entire product claims to
do — remains completely unassessed.

---

## Sequencing for items 6–10

`03`'s numbering was written before items 1–5 landed. Two of them have moved.

**Do first, before any customer:**

1. **Set Razorpay test keys and complete one checkout end to end.** Not an item
   on the list; it is the acceptance test for everything this session did, and
   it is an hour of your time. Everything below is guesswork until it passes.
2. **Item 8 — the billing correctness cluster**, but promoted and re-scoped. It
   is now the cheapest real risk reduction on the list and three of its five
   parts are one-liners:
   - RBAC on `/billing/portal` ([billing.py:251-257](../../backend/app/routers/billing.py:251)
     still has no `_rbac`, while every sibling mutation carries `require_admin_db`
     — a `viewer` can fetch the subscription-management URL). **This is a live
     access-control hole and should honestly be treated as a P1, not a polish
     item.**
   - Stop abandoned checkouts burning the trial (`_trial_available` returns
     False on *any* prior row, including an `incomplete` one from a closed
     modal).
   - Unblock resubscribe after cancel-at-period-end.
   - Stop "Select Growth" silently granting a trial.
   - Read prices from `/billing/plans` instead of hardcoding them in JSX.

**Then, in this order:**

3. **Item 7 — invoices, receipts, GST.** Promoted above plan changes. A customer
   who pays will ask for a receipt on day one, and in India a GST invoice is a
   legal requirement rather than a feature. Needs a decision from you on GSTIN
   capture (Q7, still open).
4. **Item 10 — frontend tests on the money paths.** Promoted above plan changes
   too. This session added real server-side enforcement with zero frontend
   coverage; the paywall, the billing page and the onboarding gate all carry
   revenue logic and none are tested. Also add the CI coverage gate `03` notes
   is missing. Cheap, and it protects everything just built.
5. **Item 6 — plan change: upgrade, downgrade, switch.** Still the largest
   genuine build item, still needs proration that does not exist. Demoted
   because it is a growth feature, not a launch blocker — but the UI currently
   offers "Switch to this plan" and returns 409, so until it is built, change
   the copy.
6. **Item 9 — dunning.** Depends on item 3, which now exists, so it finally has
   teeth: `past_due` is a denying state, meaning a failed payment now actually
   locks the workspace. That makes the absence of any notification worse than it
   was yesterday — a customer whose card expires gets a silent lockout. Do this
   before you have enough customers for it to matter, which is sooner than it
   sounds.

**Not on `03`'s list and worth inserting:** the `usage_metering` bug above. If
`api_request` overage is meant to be billable, that meter has never recorded a
single event.

**Still parked, and I would not start Phase 4 customization before at least
steps 1–3:** `03`'s sequencing note said not to begin customization until items
1–5 were done. They are. But "done" here means the money path works, not that it
has been proven with a real payment.
