# Payment system review — round 2

**Date:** 2026-07-21
**Scope:** live browser test + code review of the Razorpay billing path, back to front.
**Follow-on from:** `PAYMENT_AUDIT.md` (same day, static only).

---

## The headline

**Your running backend is not the code in your repo.** It predates every fix.

`GET http://localhost:8000/openapi.json` currently advertises:

```json
"StartSubscriptionBody": {
  "plan_id":       {"type": "string"},
  "billing_email": {"type": "string", "format": "email"},
  "trial_days":    {"maximum": 60, "minimum": 0, "default": 14}
}
```

Three things follow from that:

1. **`trial_days` is still caller-supplied on the live server** — the P0 trial-abuse
   hole is open right now, despite being fixed in the repo. `POST /billing/subscription
   {"trial_days": 60}` still works against your running instance.
2. **`return_path` is absent**, so none of today's changes are loaded.
3. **`/billing/subscription/verify` is not in the running route table at all**
   (only `plans`, `subscription`, `subscription/cancel`, `portal`, `usage`).
   The running build physically cannot complete a payment verification.

**Action: restart the backend.** Everything below assumes you do. Until then you are
testing a build that doesn't match the source.

---

## What I could and couldn't test live

| | |
|---|---|
| Frontend up | ✅ `localhost:5173`, renders, routes, redirects unauthenticated users to `/login` |
| Backend up | ✅ `localhost:8000/health` → `{"status":"ok"}` — but serving stale code (above) |
| Tenant session | ❌ blocked — see next section |
| Razorpay checkout | ❌ blocked — keys still blank |

### Blocker 1 — the sandbox CTA on your landing page is broken

Clicking **Try the Sandbox → Fashion & Apparel** produces `Could not launch sandbox.`
`POST /api/v1/auth/sandbox-session` returns **401**.

Cause: `settings.sandbox_email` defaults to `sandbox@sanket-dev.com`, but
`sql/004_seed.sql` only ever creates `owner@sanket-dev.com` and
`admin@sanket-dev.com`. The lookup returns NULL → `InvalidCredentialsError` → 401.

This is not just a testing inconvenience — it's the primary call-to-action on your
marketing page, and it fails for every visitor.

**Fixed:** added `backend/sql/013_sandbox_user.sql`. Seeds the user as `viewer`,
not admin — the sandbox account is publicly mintable by anyone on the internet, and
an admin there would expose the `require_admin_db` billing mutations. `password_hash`
is left NULL so `/auth/dev-login` can't be used against it.

Apply it:

```bash
docker compose exec postgres psql -U sanket_app -d sanket \
  -f /docker-entrypoint-initdb.d/013_sandbox_user.sql
```

Note: the dev tenant already has an active 10-year subscription seeded by
`011_dev_subscription.sql`, so the sandbox account will *bypass* the paywall.
To exercise checkout you need a tenant with no subscription row.

### Blocker 2 — Razorpay keys are blank

`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` are all present
but empty in `backend/.env`. You said you'd add test keys — once you do, also run
`python -m scripts.sync_razorpay_plans`, because priced plans with a NULL
`razorpay_plan_id` are now refused with a 503 by design.

### Blocker 3 — I did not create an account

Registering accounts and entering passwords is something I won't do on your behalf.
That's why I went the sandbox-token route.

---

## What was already fixed before I started

Someone had already landed the three P0s from the first audit. I verified each in
source rather than taking the audit's word for it:

- Priced plan with NULL `razorpay_plan_id` now raises `BillingNotConfiguredError` (503).
- `trial_days` removed from the request body; trial length reads from `plans.trial_days`,
  eligibility checked server-side (`_trial_available`).
- One-live-subscription-per-tenant guard plus the partial unique index in migration `0017`.
- Frontend no longer shows a success toast when checkout never opened; `onDismiss` wired.

Good work. Those were the revenue-critical ones.

---

## What I fixed this round

### Backend

**`verify_and_activate` activated on a signature alone.** A Razorpay signature only
proves the `(payment_id, subscription_id)` pair was signed with your key. It says
nothing about whether money moved, how much, or which subscription it settled. It now
calls `fetch_payment` and requires `status == "captured"`, an amount covering
`plan.base_price_cents`, and a matching `subscription_id`. New `RazorpayClient.fetch_payment`
and `RazorpayPaymentResult` support this.

**Open redirect on `redirect_url`.** The client supplied a full URL that went straight
to Razorpay as `callback_url` — the destination where signed payment results are
delivered. A tenant admin could point it at a host they controlled. The body field is
now `return_path`, validated as a relative path (rejects `//evil.com`, backslashes,
schemes), and joined server-side to `settings.app_base_url`.

**`except Exception` around signature verification.** It swallowed the "Razorpay is not
configured" `RuntimeError` from `_module()` and fell through to a manual HMAC, making
operator misconfiguration indistinguishable from a forged signature. Now catches only
the SDK's `SignatureVerificationError`; a missing secret raises.

**Webhook status was overwritten unconditionally.** The entity status was applied and
then clobbered by the event-type branch, so a `halted` subscription emitting
`subscription.charged` landed as `active` — a delinquent account with a full workspace.
The entity is now the source of truth; event type only disambiguates when the entity
carries no status. Cancellation stays terminal (Razorpay sends `subscription.cancelled`
with an entity that still reads `active` for end-of-cycle cancellations).

**No webhook ordering guard.** A delayed `subscription.activated` arriving after a
cancellation resurrected the subscription. Last-applied event timestamp is now persisted
in `subscription_metadata` and older events are dropped.

**`payment.captured` blanket-activated.** Now checks the payment entity covers the plan price.

**Yearly plans requested 120 *years* of billing.** `total_count` is a count of cycles,
not months. Added `cycles_for(billing_interval)` — 120 monthly, 10 yearly.

**Annual subscribers re-locked after 30 days.** `verify_and_activate` hardcoded a 30-day
period extension regardless of interval. Now derives from `plan.billing_interval`.

**Realtime events fired inside the transaction.** If the commit failed, every connected
client had already been told the subscription was active. Events are now buffered
(`_queue_notify`) and published by `flush_notifications()` after the session closes;
`discard_notifications()` on the error paths.

### Frontend

**Payment signature persisted in the URL.** `razorpay_payment_id` and `razorpay_signature`
were only stripped in the verify mutation's `onSuccess` — so on failure they stayed in
the URL permanently, and in every case they were in browser history and in the `Referer`
header of every subresource loaded before then. `replaceState` now runs immediately on read.

**No recovery path after a successful charge failed to verify.** The user was charged,
saw a red toast, and had nowhere to go. Added a persistent "Payment received, activation
pending" banner with a support address, in both `SubscriptionGate` and `Billing`.

**Dead air between click and modal.** `subscribe.isPending` didn't cover
`loadRazorpayScript()`'s network fetch. Added `openingCheckout`.

**Trial card was invisible to assistive tech.** `pointer-events-none` left the button in
the tab order but unreachable and unannounced. Replaced with `aria-disabled` + the
already-`disabled` button.

### Tests

`tests/test_billing.py` gains nine cases: payment not captured, underpayment,
payment belonging to another subscription, annual period extension, `halted` +
`subscription.charged`, out-of-order activation after cancellation, missing-secret
raising rather than returning False, `cycles_for`, and notification buffering.
Two existing tests were updated for the corrected webhook semantics.

`FakeRazorpayClient` now stubs `fetch_payment` and takes a `payment_result` override.

---

## Verification status — read this

- `ruff check` clean across `backend/app` and `tests/test_billing.py`.
- All touched Python files parse.
- Frontend renders; no Vite transform errors.
- **The backend test suite has NOT been run.** This sandbox has Python 3.10 and the
  project requires 3.12, and I couldn't install one (no network to the Python build
  index). Please run:

```bash
cd backend && python -m pytest tests/test_billing.py -v
```

- **`tsc --noEmit` did not complete** — it ran for several minutes against the mounted
  filesystem without finishing. Please run `npx tsc --noEmit` in `frontend/`.
  I did manually confirm no stale `redirect_url` references remain in `src/`.

I'd rather flag both of these than imply a green suite I didn't see.

---

## Still open — recommended next

### Should ship before taking real money

1. **Restart the backend.** Nothing above is live otherwise.
2. **Run migration `0017`** if not already applied. If the unique index fails, you have
   tenants holding multiple live subscriptions — dedupe first (query is in the migration docstring).
3. **Set `APP_BASE_URL`** (added to `.env.example`). Without it the callback origin falls
   back to the first `ALLOWED_ORIGINS` entry, which is `http://localhost:3000` by default —
   wrong for both dev (5173) and prod.
4. **Register the webhook** in the Razorpay dashboard: `subscription.*`, `payment.captured`,
   `payment.failed`.
5. **Redis in production.** Webhook dedupe fails open without it (`webhook_replay.py`)
   — documented as deliberate, but it silently loses dedupe. Alert on it.

### APIs that don't exist and customers will ask for on day one

| Endpoint | Why |
|---|---|
| `POST /billing/subscription/change` | The UI says "Switch to this plan" and currently gets a 409. Needs proration + cancelling the old mandate. |
| `GET /billing/invoices`, `/invoices/{id}` | No way to get a receipt. First support ticket you'll receive. |
| `POST /billing/subscription/resume` | No un-cancel before period end. |
| `GET /billing/payment-methods` | No way to see or update a card. |
| Refund webhooks | `refund.created` / `refund.processed` are unhandled — a refund leaves the subscription active. |
| Dunning | `payment.failed` sets `past_due` and tells nobody. |

### Lower priority

- **Two sources of truth for pricing.** `SubscriptionGate.tsx` hardcodes ₹4,995 / ₹14,995
  and SKU counts in JSX; `Billing.tsx` reads them from `/billing/plans`. These will drift.
  Drive the gate from the API.
- **Enterprise contact form uses `mailto:`** and shows a success toast unconditionally —
  fails silently where no mail client is configured. Should be a real endpoint.
- **`base_price_cents` is never reconciled against the Razorpay plan amount.** Your
  displayed price and the charged amount can diverge silently. Add a startup check.
- **Observability:** alert on `billing.razorpay.unknown_subscription`; track verify-failure
  rate (the signal for broken checkout); daily reconciliation of local `Subscription` rows
  against Razorpay's list.
- **E2E:** `frontend/e2e/billing.spec.ts` driving a Razorpay test card through the full flow.

---

## UI / UX assessment

The flow shape is right: plan select → email confirm → Razorpay modal (hosted-page
fallback) → verify → unlock. Nothing structurally wrong with it.

The visual design is genuinely strong — hierarchy, the "Popular" treatment on Scale,
the usage meters with 80%/100% thresholds. The billing-cycle toggle is properly built
(`role="switch"` + `aria-checked`), which is more than most teams manage. "Save 16%"
checks out: ₹49,950 vs ₹59,940 is 16.7%.

The weaknesses were all in edge states rather than the happy path, and most are now
fixed. The one remaining UX gap worth attention is the plan-change flow: the button says
"Switch to this plan" and the backend returns a 409 saying plan changes aren't supported.
Either build the endpoint or change the copy — right now the interface promises something
the system refuses.
