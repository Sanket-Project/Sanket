# 03 — State of the Product

**Date:** 2026-07-26
**Basis:** `01-codebase-map.md` (static) + `02-product-walkthrough.md` (live).
**Posture:** blunt, as requested. Nothing here is flattery.

> **AMENDED AGAIN 2026-07-27 — items 1–5 are done. Read `05-money-path-fixes.md`.**
> All five liabilities below are addressed on branch `fix/payment-money-path`
> (`d074e35`, `66eea86`, `7d349b8`, `6c18779`, `bf1f168`, `524fd29`). The
> product can now take money and enforce it. Two corrections this document
> depends on: the `/billing/plans` 500 was an unapplied migration, not the
> stale-build story; and every `[LIVE]` reading in `02`/`04` was taken against
> a bare-metal uvicorn shadowing Docker on port 8000. Go/no-go in `05`.
>
> **AMENDED 2026-07-26 — read `04-phase5-verification.md` alongside this.**
> A verification sweep corrected two findings this document leans on:
> the onboarding trap is **session-scoped, not permanent**, and the industry
> archetype **does resolve correctly after re-login** (the wrong `ind` claim is
> carried only for the first session). Liability 3 below is narrowed accordingly
> but not withdrawn. Tenant isolation was tested live and **passed all seven
> attacks**. Liabilities 1, 2, 4 and 5 are confirmed unchanged.

---

## The one-paragraph version

SANKET is an infrastructure project wearing a SaaS costume. The plumbing is
genuinely strong: row-level security with FORCE RLS, a boot-time assertion that
refuses to start if the DB role can bypass isolation, replay-protected webhooks,
fail-closed RBAC, partition maintenance, seven CI workflows. Most seed-stage
codebases have none of that. But the parts a customer touches are not finished.
You cannot currently take money. A tenant who completes onboarding is thrown back
to step one. A tenant who picks Pharmaceuticals is served the Apparel archetype
while the UI claims 21 CFR Part 11 compliance. And the subscription paywall is a
React component with no server behind it, so the product is free to anyone who
opens devtools. The gap between the engineering quality and the product
completeness is the story of this codebase.

---

## Readiness by area

| Area | Grade | Why |
|---|---|---|
| Tenant isolation | **Production-grade — now verified live** | RLS + FORCE RLS + boot-time role assertion (`database.py:116-175`). No endpoint accepts a caller-supplied `tenant_id`. Tested (`tests/test_rls_isolation.py`) **and confirmed empirically against seven attack classes on 2026-07-26 (`04`)**. |
| RBAC | **Production-grade** | Four roles, token fast-path plus DB re-check for sensitive mutations, fails closed on DB error (`rbac.py:124-128`). One gap: `/billing/portal` is unguarded. |
| Infra / CI / deploy | **Production-grade** | 7 workflows, ruff + mypy + pip-audit + pytest, kustomize overlays, staging auto-deploy, Prometheus + Grafana. No coverage gate. |
| Data model | **Production-grade** | 31 tables, sane FKs, quarterly/monthly partitioning with automated maintenance. |
| Auth | **Near production** | Firebase with dev fallback, Argon2, brute-force lockout, rate limiting. Two defects: signup echoes the password in 422 bodies, and the signup response token does not authenticate. |
| ML / forecasting | **Unassessed** | Out of scope this run. `backend/ml/` is substantial but I did not exercise it. Flagging so you do not read its absence as a pass. |
| Signals / integrations | **Demo-grade** | 11 signal connectors implemented. But the connector catalogue advertises Kafka, Snowflake, AWS, Amazon FBA; `app/services/integrations/` implements four. The UI says "30+ sources". |
| Onboarding | ~~**Broken**~~ → **Fixed, unverified in-browser** (`524fd29`) | Snapshot now rewritten on every step and rehydrated from the server; horizon seeded from the industry. The browser repro has not been re-run — needs a fresh signup. |
| Industry verticalization | ~~**Demo-grade, and misleading**~~ → **Correct in dev-fallback** (`524fd29`) | Token re-minted on industry change; verified fashion → pharma live. Firebase mode still stale. The five archetypes are still hardcoded Python — that part is unchanged. |
| **Billing** | ~~**Liability**~~ → **Functional, unproven** (`d074e35`) | Purchase path returns real responses and every guard from both payment reviews is live. **No live checkout has ever run** — Razorpay keys are blank. Plan changes still 409; no invoices, no dunning, no GST. |
| Entitlement | ~~**Liability**~~ → **Production-grade** (`bf1f168`) | `require_active_subscription` on every tenant-data router, fail-closed, 402. Verified live across the full unsubscribed sweep. |
| Frontend testing | **Absent** | Three test files total, none covering the components that carry the paywall. |

---

## The liabilities, named

**1.** ~~**You cannot take money.** `GET /billing/plans` returns 500 on the running
build, and so does `POST /billing/subscription`. Every button on the paywall is
dead. This is not a subtle bug; it is the revenue path.~~
**FIXED 2026-07-27 — `d074e35`, `6c18779`.** Cause was migration `0017` never
applied while the ORM mapped `plans.trial_days`. `/billing/plans` → 200,
`POST /billing/subscription` → 503 (correct — Razorpay keys are blank, so a
priced plan is refused rather than granted free). **No live checkout has ever
run**; that still needs test keys.

**2.** ~~**The product is free.** With no subscription at all, `/products`, `/skus`,
`/inventory/levels`, `/signals`, `/alerts`, `/financial/impact` and
`/billing/usage` all return 200. The paywall is `SubscriptionGate.tsx`, a React
component. Nothing enforces entitlement server-side. Any customer who churns
keeps full access. Any customer who reads the network tab never has to pay.~~
**FIXED 2026-07-27 — `bf1f168`.** `require_active_subscription` applied to every
tenant-data router. Verified live: all seven endpoints now 402 for a tenant with
no subscription. `/billing/usage` stays 200 by decision (gating any billing
route deadlocks checkout; it returns nulls unsubscribed).

**3.** ~~**The compliance claim is false during a tenant's first session.**~~
**FIXED 2026-07-27 — `524fd29`** in dev-fallback mode. `/industry/activate`
re-mints the token with the new `ind`; verified live fashion → pharma, horizon
26 → 52. **Firebase mode is still stale** (custom claims are set at
provisioning) and there is no Firebase project to verify a fix against — so
**the "do not sell into pharma" guidance stands until you can confirm this in
whichever auth mode you actually ship.**
*(Narrowed 2026-07-26 — see `04`. Originally written as permanent; it is not.)*
The JWT is minted at login and not re-minted when onboarding sets the industry, so
for the remainder of that first session a pharma tenant is served the fashion
archetype (26-week horizon, fashion signals, **standard audit level**) while the
header renders `GXP · 21 CFR PART 11`. After re-login everything resolves
correctly.

The window is one session, but it is the session in which a new tenant runs their
baseline forecast. For a validated-systems buyer, an audit level that silently
differs from the badge on screen is still a finding, and "it corrects itself if
you log out" is not an answer that survives a quality audit. **Guidance unchanged:
fix this before selling into pharma.**

**4.** ~~**Your security fixes are uncommitted and therefore unshippable.**~~
**FIXED 2026-07-27 — `d074e35`, `66eea86`.** And the reason they were never
committed is now known: a **zero-byte `.git/index.lock` dated 2026-07-21**, left
by the crashed round-2 review session, made every `git add` in this repository
fail for six days. Not withheld, not forgotten — mechanically unable to land.
`/health` now reports the running build's git SHA so a stale deployment is
detectable without guessing.
`PAYMENT_REVIEW_ROUND2.md` told you on 21 July that the live backend predated
every payment fix. It still does, and I found out why: those fixes were never
committed. `git log` HEAD is `65023e1` (the Sanket rebrand); `git show
HEAD:backend/app/routers/billing.py` still contains
`trial_days: int | None = Field(default=14, ge=0, le=60)`. There are **462
uncommitted lines** across `billing.py` and `subscription_manager.py`.

`build-images.yml` builds from the committed tree, so staging and production
would never receive these fixes regardless of how many times you deploy. Two
payment reviews have produced work that physically cannot ship. **The process gap
is more serious than any individual bug on this list.**

**5.** ~~**Passwords land in error responses.** A 422 on signup returns the submitted
password in plaintext inside `detail[].input`. That reaches the browser, and from
there any error-tracking SDK or proxy log you ever add.~~
**FIXED 2026-07-27 — `7d349b8`.** Global `RequestValidationError` handler strips
`input` and `ctx`, keeps `loc`/`msg`/`type`. Covers every credential-taking
endpoint, not just signup.

---

## What is genuinely good

Stating this plainly because the list above is long and the engineering deserves
the credit.

- The isolation model is correct **by construction**, not by discipline. The
  boot-time assertion (`database.py:116-175`) means a misconfigured
  `DATABASE_URL` cannot silently disable tenant isolation in production. Very few
  teams do this.
- The billing **source code** handles the hard parts properly: payment capture
  confirmation, amount matching, subscription-ownership verification, webhook
  replay protection, out-of-order event guards, post-commit notification
  flushing. Someone thought carefully about the failure modes. The problem is
  breadth and deployment, not craft.
- Error copy is above average. *"No active SKUs found for industry 'pharma'.
  Import products/SKUs (CSV upload or a connector) before forecasting."* names the
  problem, the context, and the fix.
- CI discipline is real: lint, format, types, dependency audit, tests, image
  scanning, staged deploys.

---

## Top 10, in priority order

Effort is given at two scales: **human-team hours**, and **agent-assisted**
(Claude Code doing the work with review). Both assume one competent reviewer.

> **Items 1–5 are DONE as of 2026-07-27** on `fix/payment-money-path`. Struck
> through below with their SHAs. Items 6–10 are unchanged and un-started;
> re-sequenced at the end of `05`.

| # | Fix | Why it is here | Human | Agent |
|---|---|---|---|---|
| ~~1~~ | ~~**Commit the 462 uncommitted payment-fix lines, deploy, verify**~~ **DONE `d074e35` + `66eea86`** | Not "restart" — the fixes are not in `HEAD`, so images built by `build-images.yml` will never contain them. Review the diff, commit, push, confirm staging, then re-run this audit's P0 list. Add a `/health` field exposing the running git SHA so this cannot recur silently. | 4h | 45m |
| ~~2~~ | ~~**Fix `GET /billing/plans` 500**~~ **DONE `d074e35` + `6c18779`** | Nothing else in billing is testable until this works, and no customer can pay. **Narrowed 2026-07-26:** every path that reads the `plans` table 500s; no other billing path fails. Leading hypothesis is that the DB is behind migration `0010` and lacks `razorpay_plan_id`. Four confirming commands are in `04` §P0-2 — run them first. | 2-4h | 30m |
| ~~3~~ | ~~**Server-side entitlement**~~ **DONE `bf1f168`** | One `require_active_subscription` dependency, applied to every tenant-data router in `main.py:365-399`. Reads status ∈ (active, trialing) and `current_period_end > now()`. Add tests for cancelled, past_due, and expired. | 1-2d | 2h |
| ~~4~~ | ~~**Refresh session state after onboarding**~~ **DONE `524fd29`** | One root cause behind two P0s (#3 and #4 in `02`). Reissue the token (or resolve `ind` from the DB per request) and rehydrate the auth store from `GET /onboarding/state` rather than the signup-time localStorage snapshot. | 1-2d | 3h |
| ~~5~~ | ~~**Strip `input` from validation error bodies**~~ **DONE `7d349b8`** | Custom `RequestValidationError` handler in `main.py`. Minutes of work, removes a plaintext-password leak. | 1h | 10m |
| 6 | **Plan change: upgrade, downgrade, switch** | Currently raises `PlanChangeNotSupportedError` unconditionally while the UI offers four plans. Includes proration, which does not exist. This is the largest genuine build item on the list. | 1-2wk | 2-3d |
| 7 | **Invoices, receipts, billing email, GST** | None exist. For B2B SaaS billing in INR this is a legal requirement, not a feature. Needs a decision on GSTIN capture. | 1-2wk | 2-3d |
| 8 | **Billing correctness cluster** | RBAC on `/billing/portal`; stop abandoned checkouts burning the trial; unblock resubscribe after cancel-at-period-end; stop "Select Growth" silently granting a trial; read prices from `/billing/plans` instead of hardcoding them in JSX. Five small fixes, one PR. | 2-3d | 4h |
| 9 | **Dunning and failed-payment recovery** | `payment.failed` sets `past_due` and nothing else happens. No retry schedule, no notification, no grace-period expiry. Depends on #3 to have any teeth. | 3-5d | 1d |
| 10 | **Frontend test coverage on money paths** | Three test files today. The paywall, the onboarding gate, and the billing page all carry revenue or access logic and none are tested. Add Playwright coverage for subscribe, cancel, gate-blocks-unpaid. Add a coverage gate to CI. | 3-5d | 1d |

**Sequencing note.** Items 1 through 5 are roughly one week of agent-assisted
work and take the product from "cannot take money and is free to everyone" to
"can take money and enforces it". Do not start Phase 4 customization work before
that week is done. Reasoning is in `docs/strategy/customization-plan.md`.

---

## What I did not assess

Being explicit so you do not read silence as approval:

- The ML stack (`backend/ml/`), model quality, and forecast accuracy.
- Performance and load behaviour. No load test exists.
- The WebSocket realtime layer under concurrency.
- The 11 external signal connectors against live APIs.
- ~~Live cross-tenant data access~~ — **completed 2026-07-26, PASSED.** Seven
  attacks (header spoofing, direct-UUID read, cross-tenant mutation, JWT `tid`
  forgery, `alg:none`) all repelled. See `04`.
- Accessibility. `design:accessibility-review` exists and this product has not had
  a WCAG pass.
