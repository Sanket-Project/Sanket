# 02 — Product Walkthrough

**Date:** 2026-07-26
**Environment:** `http://localhost:5173` (SPA) → Vite proxy → `http://127.0.0.1:8000` (API)
**Method:** cold signup as a brand-new tenant, full onboarding, then direct API
probing with that tenant's own session token.
**Test identities used:** `qa-alpha@example.com` (tenant `53c83b38-…`),
`qa-gamma@example.com` (tenant `d632cfe9-…`). No real personal data, no real
payment instrument, no live Razorpay keys.

---

## 0. Blocking context — the running backend is not your source code

`PAYMENT_REVIEW_ROUND2.md` said this on 2026-07-21. **It is still true today.**

`GET http://localhost:8000/openapi.json` currently advertises:

```json
"StartSubscriptionBody": {
  "plan_id":       {"type": "string"},
  "billing_email": {"type": "string", "format": "email"},
  "trial_days":    {"anyOf": [{"type":"integer","maximum":60,"minimum":0},
                              {"type":"null"}], "default": 14}
}
```

Billing routes in the live route table: `plans`, `subscription`,
`subscription/cancel`, `portal`, `usage`. **91 paths total.**

Three consequences:

1. `trial_days` is still caller-supplied on the live server. The P0 trial-abuse
   hole that `billing.py:45-50` closed in source is **open on the running
   instance**.
2. `return_path` is absent, so the callback-hijack fix
   (`billing.py:52-62`) is not loaded.
3. `POST /billing/subscription/verify` **does not exist** in the live route
   table. The running build physically cannot complete a payment verification —
   `SubscriptionGate.tsx:105` calls it and would always fail.

### Root cause, found on the verification pass

**The payment fixes were never committed.** They exist only as uncommitted
changes in your working tree:

```
$ git log --oneline -1
65023e1 feat: rebrand project assets to Sanket, update CI/CD workflows, …

$ git diff --stat -- backend/app/routers/billing.py \
                     backend/app/services/billing/subscription_manager.py
 backend/app/routers/billing.py                  | 122 ++++++-
 .../app/services/billing/subscription_manager.py| 369 +++++++++++++++++++--
 2 files changed, 462 insertions(+), 29 deletions(-)

$ git show HEAD:backend/app/routers/billing.py | grep trial_days
27:    trial_days: int | None = Field(default=14, ge=0, le=60)
```

`HEAD` still carries the vulnerable `trial_days` field, which is exactly what the
live `openapi.json` advertises. 462 lines of security fixes are sitting
uncommitted.

**This is worse than a stale process.** A restart would pick them up locally
because of the bind mount, but `build-images.yml` builds from the committed tree,
so **staging and production would never receive these fixes no matter how many
times you deploy.** Two payment reviews have produced work that cannot ship.

**Action: commit and push the working tree, then verify staging.** Restarting
alone is not sufficient.

**Everything below marked [LIVE] was observed against this stale build.**
Findings marked [SOURCE] come from the repository working tree and are
independent of it.

---

## P0 — ship-blocking

### P0-1 [SOURCE + LIVE] ~~Entitlement is enforced only in React. Every paid API is open.~~

> **FIXED 2026-07-27 — `bf1f168`.** One `require_active_subscription`
> dependency (`app/core/entitlement.py`) applied at `include_router` to every
> tenant-data router. Re-ran the sweep below live against the rebuilt image:
> all seven endpoints now return **402**. `/billing/usage` stays 200 by
> decision — gating any billing route deadlocks checkout and it returns nulls
> for an unsubscribed tenant. Authority is `subscriptions`, not `tenants.tier`;
> reasoning in `05`. Tests: `backend/tests/test_entitlement.py`.

The paywall is a client-side component. There is no server-side subscription
check anywhere in the backend.

**Evidence — code:** `grep -rn "SubscriptionGate\|require_subscription\|entitle"
backend/app/` returns **only comments** (`subscription_manager.py:184`). The gate
is `frontend/src/components/auth/SubscriptionGate.tsx:36`, mounted at
`frontend/src/components/layout/AppShell.tsx:42`.

**Evidence — live.** As tenant `qa-alpha`, with the paywall overlay on screen and
`GET /api/v1/billing/subscription` returning `null` (no subscription row at all):

| Endpoint | Status |
|---|---|
| `/api/v1/products` | **200** `[]` |
| `/api/v1/skus` | **200** `[]` |
| `/api/v1/inventory/levels` | **200** `{"industry":"fashion","count":0,…}` |
| `/api/v1/signals` | **200** `[]` |
| `/api/v1/alerts` | **200** `[]` |
| `/api/v1/webhooks/endpoints` | **200** `[]` |
| `/api/v1/financial/impact` | **200** `{"industry":"fashion",…}` |
| `/api/v1/billing/usage` | **200** full meter payload |

**Repro:** sign up cold → do not subscribe → open devtools →
`fetch('/api/v1/products',{headers:{Authorization:'Bearer '+localStorage.getItem('sanket.dev.token')}})`
→ 200.

**Impact:** a cancelled, expired, past-due, or never-paid tenant retains full API
access. Anyone who can read the network tab can use the product for free. This
also means "does downgrading revoke access?" has the same answer for every plan
transition: **no, nothing is revoked, because nothing was ever enforced.**

**Root cause:** no `require_active_subscription` FastAPI dependency exists. Needs
one, applied to every tenant-data router in `app/main.py:365-399`, reading
`Subscription.status ∈ (active, trialing)` and `current_period_end > now()`.

---

### P0-2 [LIVE] ~~`GET /billing/plans` returns 500. The entire purchase path is dead.~~

> **FIXED 2026-07-27 — `d074e35` + `6c18779`.** Root cause was **not** the
> assumption below, and not `04`'s hypothesis either. `models/billing.py:45`
> maps `plans.trial_days` while migration `0017`, which adds it, had never been
> applied — `asyncpg.UndefinedColumnError` on every ORM read of `plans`. `0017`
> is now committed and applied. `/billing/plans` → **200**;
> `POST /billing/subscription` → **503** (correct: Razorpay keys are blank, so
> the misconfiguration guard refuses a priced plan rather than granting it
> free). `/health/detailed` now reports migration drift so this cannot hide
> again.
>
> **Also correcting the environment:** the 500 was observed against a
> bare-metal uvicorn on Python 3.14 that was shadowing Docker on
> `127.0.0.1:8000`. See `05` — every `[LIVE]` reading in this document came
> from that process.

```
GET  /api/v1/billing/plans        -> 500 {"detail":"An unexpected error occurred"}
POST /api/v1/billing/subscription -> 500 {"detail":"An unexpected error occurred"}
```

Every button on the paywall — Start Free Trial, Select Growth, Select Scale —
routes into one of these. A new customer who wants to pay you **cannot**.

**[ASSUMPTION]** on cause: the stale application code and the migrated database
disagree about the `plans` table shape (migration `0017_billing_p0_guards.py:66`
added `trial_days`; `0010_stripe_to_razorpay.py` reshaped the provider columns).
The 500 body is generic, so I could not confirm without server logs. **Please
check the backend log for the traceback.**

This also explains why `SubscriptionGate.tsx` hardcodes prices (see P1-6) — the
plans API has presumably been broken long enough that someone worked around it.

---

### P0-3 [LIVE + SOURCE] ~~A tenant that completes onboarding is trapped back at Step 1 forever.~~

> **SUPERSEDED 2026-07-26 by `04-phase5-verification.md`.** The repro below is
> correct but **"forever" was wrong** — logging out and back in clears it. The
> real scope is: any **full page load** (F5, typed URL, new tab) rehydrates the
> stale snapshot and bounces the tenant; SPA-internal navigation works. Exact root
> cause: `sanket.dev.session` is written only at `stores/auth.ts:206,242`
> (login/signup); `setOnboarding` (`:110`) updates memory only. Still P0. See `04`.
>
> **FIXED 2026-07-27 — `524fd29`.** `setOnboarding` now also rewrites the
> persisted blob, and `bootstrap()` re-reads `GET /onboarding/state` on both
> the Firebase and dev-fallback paths, so the server is authoritative rather
> than the login-time snapshot. **The browser repro below has not been re-run**
> — it needs a fresh signup, which means typing a password. Please confirm by
> hand.

**Repro:**
1. Sign up cold at `/login?mode=signup`.
2. Complete all five onboarding steps, click **Finish setup**. You land on
   `/workspace`. Correct.
3. Navigate to `/workspace/billing`, or reload any page.
4. You are redirected to `/onboarding`, Step 1, with all five sidebar steps
   showing **incomplete**.

**The server disagrees.** `GET /api/v1/onboarding/state` returns:

```json
{"status":"complete","current_step":"done",
 "steps":{"industry":{"done":true,"at":"2026-07-26T13:15:23.601374Z",
                      "meta":{"industry":"pharma"}}, …}}
```

**Root cause:** `frontend/src/components/auth/OnboardingGate.tsx:12` reads
`onboarding` from the Zustand auth store —
`useAuthStore((s) => s.onboarding)` — which is hydrated from the
`sanket.dev.session` localStorage blob written **once at signup**. The wizard
persists completion to the server but never refreshes that snapshot, so the
stale `status: "in_progress"` wins on every remount.

**Impact:** every new self-serve customer hits this on their second page load.

---

### P0-4 [LIVE + SOURCE] ~~The industry you choose is never applied. A pharma tenant is served as fashion.~~

> **SUPERSEDED 2026-07-26 by `04-phase5-verification.md`. This was overstated and
> is the most important correction in the audit.** After re-login the archetype
> resolves **correctly**: `ind: pharma`, `effective_horizon: 52`, pharma signal
> types, pharma granularity dimensions. The defect is that the JWT is minted at
> login and not re-minted when onboarding sets the industry, so the wrong `ind`
> is carried only for the remainder of that first session (~1h token life).
> **Downgraded P0 → P1.** The compliance concern survives in narrowed form: the
> first session is when a tenant runs their baseline forecast, and during it the
> audit level silently differs from the `21 CFR PART 11` badge. See `04`.
>
> **FIXED 2026-07-27 — `524fd29`.** `POST /industry/activate` now returns a
> re-minted token carrying the new `ind`, and `StepIndustry` swaps it in.
> Verified live: `ind` fashion → pharma, `/industry/profile` 26-week → 52-week.
> Re-minting was chosen over per-request DB resolution so the deny-by-default
> `X-Industry-Code` control keeps a single source of truth — reasoning in `05`.
> **Firebase mode is still stale** (custom claims set at provisioning); no
> Firebase project exists to verify a fix against.

I selected **Pharmaceuticals** at onboarding Step 1. The workspace header
renders `Pharmaceuticals` and a green `GXP · 21 CFR PART 11` badge.

The backend disagrees:

```
JWT claims:            "ind": "fashion"
GET /industry/profile: {"code":"fashion","display_name":"Apparel & Fashion",
                        "effective_horizon":26,
                        "active_signal_types":["trend_search","social_sentiment",
                                               "weather","competitor_price"],
                        "feature_flags":{"markdown_optimizer":true,
                                         "assortment_planning":true}}
GET /inventory/levels: {"industry":"fashion",…}
GET /financial/impact: {"industry":"fashion","horizon_weeks":12,…}
```

Onboarding *did* record the choice — `steps.industry.meta.industry == "pharma"` —
but the JWT is never reissued after signup, and `ind` is baked in at token mint
time (`app/middleware/tenant_context.py:107`).

**Impact.** A pharma tenant silently receives:

- 26-week horizon instead of 52 (`industry_context.py:105`)
- fashion demand signals instead of pharma's (`industry_context.py:107`)
- fashion feature flags (`markdown_optimizer`, `assortment_planning`)
- **standard audit level instead of GxP**

while the UI asserts 21 CFR Part 11 compliance. For a regulated vertical this is
a compliance defect, not a UX defect. I would not demo this to a pharma buyer.

**Root cause:** same as P0-3 — session state is written once at signup and never
refreshed. Fix requires reissuing the token (or resolving `ind` from the DB
per-request rather than from the claim) after the industry step commits.

---

### P0-5 [LIVE] ~~Signup echoes the submitted password in plaintext in its 422 body.~~

> **FIXED 2026-07-27 — `7d349b8`.** Custom `RequestValidationError` handler in
> `main.py` keeps `loc`, `msg`, `type` and drops `input` and `ctx`. Global, so
> it covers dev-login and password reset too.
> Tests: `backend/tests/test_validation_errors.py`.

> **BROADENED 2026-07-26 by `04-phase5-verification.md`.** Not just signup.
> `POST /api/v1/auth/dev-login` leaks identically, confirming this is the global
> FastAPI `RequestValidationError` handler and therefore affects **every**
> endpoint that accepts a password, including password reset. Severity raised.

```
POST /api/v1/auth/signup   {"email":"leak-probe@example.com","password":"SuperSecret!123"}

422 {"detail":[{"type":"missing","loc":["body","name"],"msg":"Field required",
                "input":{"email":"leak-probe@example.com",
                         "password":"SuperSecret!123"}}, …]}
```

FastAPI's default `RequestValidationError` handler serialises the offending
`input` object, password included. That payload reaches the browser, and from
there any error-tracking SDK, proxy log, CDN log, or support screenshot.

**Fix:** register a custom `RequestValidationError` handler in `app/main.py` that
strips `input` (or redacts known-sensitive keys) before serialising. Cheap fix,
high severity.

---

## P1 — fix before launch

### P1-1 [SOURCE] Plan changes are not implemented, but the UI offers them.

`subscription_manager.py:113-117` raises `PlanChangeNotSupportedError`
unconditionally when a tenant with a live subscription requests a different plan.
The paywall renders four selectable plans regardless. Upgrade, downgrade, and
mid-cycle switch all 409.

**Consequence for the Phase 2 brief:** proration cannot be tested because there
is no proration code anywhere in `app/services/billing/`. There is nothing to
test.

### P1-2 [SOURCE] Cancel-at-period-end permanently blocks resubscription.

`cancel(at_period_end=True)` sets the flag but leaves `status` untouched
(`subscription_manager.py:219-222`). The row therefore still matches
`LIVE_STATUSES` (`:37-41`), so `_live()` finds it (`:458`) and any subsequent
`start_subscription` on a different plan raises `PlanChangeNotSupportedError`
(`:113`). The tenant is stuck until Razorpay's terminal event arrives — which,
on the live build, it cannot, because webhook-driven activation depends on the
missing verify path.

### P1-3 [SOURCE] An abandoned checkout permanently burns the tenant's trial.

`_trial_available` returns False if **any** prior `subscriptions` row exists
(`subscription_manager.py:480-483`), including an `incomplete` row from a
checkout the user closed. One misclick costs the trial forever, with no
self-serve recovery.

### P1-4 [SOURCE] `POST /billing/portal` has no RBAC guard.

`app/routers/billing.py:251-257` takes `body`, `request`, `tenant_id`,
`settings` — and no `_rbac`. Compare `start_subscription` (`:142`),
`verify_subscription` (`:202`), `cancel_subscription` (`:233`), all of which
carry `require_admin_db`. Any tenant member, **including a `viewer`**, can obtain
the Razorpay subscription-management URL.

### P1-5 [SOURCE] "Select Growth" gives a free trial instead of taking payment.

Migration `0017_billing_p0_guards.py:66` runs
`UPDATE plans SET trial_days = 14 WHERE base_price_cents > 0`, and trial length
comes from the plan (`subscription_manager.py:125`). The trial card
(`SubscriptionGate.tsx:380`) and the Growth card (`:422`) post the **same**
`plan_id`, `growth_monthly` — the second argument to `handleSelectPlan` is
cosmetic. A first-time tenant who deliberately chooses to pay gets 14 free days.

### P1-6 [SOURCE] Prices are hardcoded in the UI and never read from the API.

`SubscriptionGate.tsx:402` (`₹4,995`), `:447` (`₹14,995`), `:369`, `:369`. The
component never calls `/billing/plans`. Three sources of truth — the JSX, the
`plans` table, and the Razorpay dashboard — with nothing reconciling them. See
also open question Q10.

### P1-7 [LIVE] ~~Onboarding ignores the industry's forecast horizon.~~

> **FIXED 2026-07-27 — `524fd29`.** `StepCalendar` now seeds `horizon_weeks`
> from the industry's `effective_horizon`. A saved planning config still wins.

Step 1 advertises **"52-wk horizon"** on the Pharmaceuticals card
(`StepIndustry.tsx:109` renders `meta.default_horizon_weeks`). Step 3 then
presents Forecast Horizon pre-filled with **13**, because
`StepCalendar.tsx:53` hardcodes `horizon_weeks: 13` for every industry. The
wizard contradicts itself two screens apart.

### P1-8 [LIVE] Validation errors attach to the wrong field. — **ROOT-CAUSED 2026-07-27, not fixed**

> It is **not** a loc-to-field mapping bug; there is no mapping at all.
> `getErrorMessage` (`utils/errors.ts`) joins every message into one string, and
> `Login.tsx` binds that single shared `error` state straight to a password
> input on both forms — `:444` (sign-in Password) and `:549` (sign-up Confirm
> password) — with no form-level alert region anywhere in the file. So every
> server error, the email one included, renders under a password field.
> Fix shape: add a form-level alert, leave only the local "Passwords do not
> match" check bound to Confirm password. Deferred because `Login.tsx` carries
> 440 uncommitted unreviewed lines. See `05`.

**Repro:** signup with email `qa-alpha@example.test`. The message
*"value is not a valid email address: The part after the @-sign is a special-use
or reserved name that cannot be used with email"* renders **under CONFIRM
PASSWORD**, with the red error border on Confirm Password. Screenshot captured.

Two problems: the field mapping is wrong, and the raw `email-validator` library
string is being surfaced verbatim to an end user.

### P1-9 [LIVE] The token returned by `POST /auth/signup` does not authenticate.

The `access_token` in the signup response returns
`401 {"detail":"Token is invalid or has expired"}` on every endpoint, while the
separately-stored `sanket.dev.token` works. Reproduced twice, on two fresh
tenants. **This blocked my live cross-tenant isolation test** — see §"Not tested".
**[ASSUMPTION]** this is a dev-mode token-minting quirk rather than a production
path, but it should not be shipping in either.

---

## P2 — polish

- **P2-1** `/signup` is a 404. Signup lives at `/login?mode=signup`
  (`App.tsx:148`, `Login.tsx:177`). Any marketing link or bookmark to `/signup`
  dies.
- **P2-2** The landing page renders empty skeleton cards for ~3s before content.
- **P2-3** Onboarding step transitions render the **previous** step's body under
  the **next** step's heading for ~1s (captured between Step 2 and Step 3).
- **P2-4** After a failed baseline run, the status pip still reads
  **"Forecast engine ready"** in green next to a red "Forecast run failed".
- **P2-5** The signup form asks for a **WORKSPACE** slug ("acme-co", "Lowercase,
  numbers & hyphens") before asking anything a customer recognises. A supply-chain
  planner does not know what a slug is. Ask for a company name and derive it.
- **P2-6** Signup never asks which industry the tenant is in, despite industry
  being the single most important piece of tenant context in this product. It is
  deferred to onboarding Step 1 — which is then discarded anyway (P0-4).
- **P2-7** Onboarding Step 2 advertises *"Connect Shopify, Amazon FBA, and 30+
  sources"*. `app/services/integrations/` implements four: Shopify, WooCommerce,
  generic SQL, and file import. **Amazon FBA does not exist.** See Q9.
- **P2-8** A new tenant shows "1 / 5 seats used" before any subscription exists,
  implying a plan they have not bought.

---

## What works well

Worth stating plainly, because the list above is long:

- **Signup → onboarding → workspace completes end-to-end** on the first pass.
  The wizard is clean, the five industries are all present, and the copy is good.
- **Error handling on the empty-catalog baseline run is excellent.** *"No active
  SKUs found for industry 'pharma'. Import products/SKUs (CSV upload or a
  connector) before forecasting."* — states the problem, names the industry,
  gives the fix.
- **Tenant isolation has no ID-manipulation surface.** No endpoint in
  `app/routers/` accepts a caller-supplied `tenant_id`; every tenant-scoped route
  derives it from `request.state` via the `TenantId` dependency
  (`industry_router.py:66`). Combined with RLS + `FORCE ROW LEVEL SECURITY`
  (`0011_reconcile_schema_and_force_rls.py:155`) and the boot-time role assertion
  (`database.py:116-175`), the isolation model is sound by construction.
- **`X-Industry-Code` switching is deny-by-default** and correctly validated
  against the token's `industries` claim (`tenant_context.py:114-138`).
- **The billing source code handles the genuinely hard parts correctly** — payment
  capture confirmation, amount matching, subscription-ownership checks, webhook
  replay protection, event ordering, and post-commit notification flushing. The
  problem is that this code is not what is running, and that breadth is missing.

---

## Payment findings — consolidated

Because this section was called out specifically.

| # | Finding | Sev | Live or source |
|---|---|---|---|
| P0-1 | No server-side entitlement enforcement at all | P0 | both |
| P0-2 | `/billing/plans` and `POST /billing/subscription` 500 | P0 | live |
| — | `trial_days` still caller-supplied (max 60) | P0 | live only — fixed in source |
| — | `/billing/subscription/verify` missing from route table | P0 | live only — exists in source |
| P1-1 | No upgrade / downgrade / plan switch | P1 | source |
| — | No proration logic exists | P1 | source |
| P1-2 | Cancel-at-period-end blocks resubscribe | P1 | source |
| P1-3 | Abandoned checkout burns the trial | P1 | source |
| P1-4 | `/billing/portal` missing RBAC | P1 | source |
| P1-5 | Paid plan silently grants a trial | P1 | source |
| P1-6 | Prices hardcoded in the UI | P1 | source |
| — | No invoices, receipts, or emails | P1 | source |
| — | No dunning beyond setting `past_due` | P1 | source |
| — | No tax / GST handling | P1 | source |
| — | `_payment_covers_plan` fails open on missing `amount` (`:434-435`) | P2 | source |

**On DB-vs-provider drift:** the reconciliation logic in
`handle_razorpay_event` (`subscription_manager.py:327-418`) is well built —
ordering guard, entity-as-truth, terminal-event override. I could not exercise it
live because Razorpay keys are blank and the verify route is missing from the
running build. **Verdict: cannot confirm; the code reads correct.**

---

## Not tested, and why

| Not tested | Reason |
|---|---|
| Live checkout on any plan tier | `/billing/plans` 500s; no Razorpay test keys (Q6) |
| Declined / insufficient-funds / 3DS card | No Razorpay sandbox keys |
| Upgrade, downgrade, proration | Not implemented (P1-1) |
| Cancel → resubscribe | Cannot subscribe in the first place (P0-2) |
| Invoices, receipts, billing emails | Do not exist |
| Webhook reconciliation end-to-end | Requires a live Razorpay sandbox |
| ~~**Live cross-tenant read**~~ | ~~Blocked by P1-9~~ — **DONE 2026-07-26, see `04`.** Worked around via `/auth/dev-login`. Seven attacks run (header spoof ×4, direct-UUID read, cross-tenant PATCH/DELETE, JWT `tid` forgery, `alg:none`). **All repelled.** Isolation confirmed live. |
| Per-industry feature depth (5 verticals) | Blocked by P0-4 — every tenant is served as `fashion` regardless of choice |

---

## Suggested fix order

> **Updated 2026-07-26.** Step 1 below was re-tested: the build is unchanged, and
> the cause is that the fixes were never committed. See `04` for the corrected
> P0 scorecard before working this list.

1. **Commit and deploy the payment workstream**, then re-verify. Restarting is not
   sufficient — the fixes are not in `HEAD`.
2. Fix `/billing/plans` 500 (P0-2) — nothing else in billing can be tested until
   this works.
3. Add a `require_active_subscription` dependency (P0-1).
4. Refresh session state after onboarding (P0-3 and P0-4 share one root cause).
5. Strip `input` from validation error responses (P0-5) — one handler, minutes of
   work.
6. Then the P1 billing gaps, in the order listed.
