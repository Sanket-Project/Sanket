# Payment / Billing Audit — SANKET (Razorpay integration)

**Date:** 2026-07-21
**Scope:** `backend/app/routers/billing.py`, `backend/app/services/billing/*`, `frontend/src/pages/Billing.tsx`, `frontend/src/components/auth/SubscriptionGate.tsx`, `frontend/src/utils/razorpay.ts`, `frontend/src/api/billing.ts`, `backend/sql/005_phase5_realtime_billing.sql`
**Method:** static review. **Live browser test was not possible** — see "Blockers" below.

---

## Blockers on live testing

1. **Nothing is running.** `http://localhost:8000` (API) and `http://localhost:5173` (web) both refuse connections. The stack needs to be up before any UI/flow test.
2. **Razorpay is not configured.** `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` are absent from `.env` — and are not even present in `.env.example`, so a new developer has no signal they're required. `GET /billing/config` therefore returns `configured: false`, the Razorpay checkout modal never opens, and no payment can be exercised end-to-end.
3. **Creating a sign-in account with a made-up email is something I won't do on your behalf** (account creation). There is a dev-token path (`mint_dev_token` in `app/core/firebase_auth.py`, exercised by `test_sandbox_session_returns_dev_token`) and a seeded dev tenant (`sql/011_dev_subscription.sql`) — point me at either and I can drive the flow without registering anything.

The static review below is complete and does not depend on the above.

---

## P0 — Paid plans currently grant full access with zero payment

**This is the finding that matters.** It is a live revenue leak, not a theoretical one.

The chain:

| Step | Location | Behaviour |
|---|---|---|
| 1 | `sql/005_phase5_realtime_billing.sql:61` | All five plans are seeded with `razorpay_plan_id` **NULL** — the INSERT never populates that column. |
| 2 | `.env` | No Razorpay creds ⇒ `scripts/sync_razorpay_plans.py` (the only thing that backfills `razorpay_plan_id`) has never been run. |
| 3 | `subscription_manager.py:66` | `if plan.razorpay_plan_id:` is **falsy for every plan** ⇒ always takes the `else` branch. |
| 4 | `subscription_manager.py:90-111` | The `else` branch, with `trial_days=0`, sets `status = SubscriptionStatus.active` and `period_end = now + 30 days`. **No Razorpay call. No payment. No card.** |
| 5 | `SubscriptionGate.tsx:153` | `hasAccess = sub.status === "active"` ⇒ workspace unlocked. |

**Reproduction (once the stack is up):** log in as any tenant → gate appears → "Select Scale" → enter any email → "Proceed to Payment" → you now have an active ₹14,995/month Scale subscription, free, forever-ish. The UI even shows `toast.success("Subscription activated successfully!")` because `short_url` is null.

That `else` branch was written for enterprise/custom-billed plans (`base_price_cents == 0`), but nothing restricts it to them.

**Fix:**

```python
# subscription_manager.py, start_subscription
if plan.base_price_cents > 0 and not plan.razorpay_plan_id:
    raise RuntimeError(
        f"Plan '{plan_id}' is priced but has no razorpay_plan_id — "
        "run scripts/sync_razorpay_plans.py before accepting subscriptions."
    )
```

and in the local branch, never emit `active` for a priced plan — use `SubscriptionStatus.incomplete`. Add a startup health check that fails loudly if any `is_active` plan with `base_price_cents > 0` lacks a `razorpay_plan_id`.

---

## P0 — `trial_days` is client-controlled

`StartSubscriptionBody.trial_days` (`billing.py:27`) is supplied by the request body, `ge=0, le=60`. The UI sends 14 or 0, but the API accepts anything in range from a crafted request. Trial re-use is blocked **only client-side** (`SubscriptionGate.tsx:219`, `hasTrialHistory = !!sub`); the server never checks for prior trials.

So: `POST /billing/subscription {"plan_id": "scale_yearly", "trial_days": 60}`, repeatedly.

**Fix:** remove `trial_days` from the request body entirely. Add a `trial_days` column to `plans` and read it there. Enforce one-trial-per-tenant server-side by querying for any prior `Subscription` row for the tenant.

---

## P0 — No idempotency; duplicate subscriptions and double billing

`start_subscription` never checks whether the tenant already has an active or trialing subscription. Two clicks on "Proceed to Payment" (the button has a loading state but the mutation isn't guarded against a second mount) create two Razorpay subscriptions. `get_subscription` returns only the newest by `created_at`, so the orphaned one keeps billing invisibly.

**Fix:**
- Guard at the top of `start_subscription`: if an active/trialing/past_due sub exists, return it rather than creating another.
- Partial unique index: `CREATE UNIQUE INDEX ON subscriptions (tenant_id) WHERE status IN ('trialing','active','past_due');`
- Pass an idempotency key to Razorpay derived from `(tenant_id, plan_id)`.

---

## P1 — Server-side open redirect via `redirect_url`

`redirect_url` is taken from the request body (`billing.py:28`) and passed straight to Razorpay as `callback_url` (`razorpay_client.py:117`). The frontend validates `short_url` on the way *back* (`isSafeRedirectUrl`), but **nothing validates what goes out**. That callback URL is where Razorpay delivers `razorpay_payment_id` and `razorpay_signature` as query params — so a tenant admin can redirect a signed payment result to a domain they control.

**Fix:** ignore the client value. Construct the callback from a configured `APP_BASE_URL`, or at minimum allowlist against `settings.allowed_origins` server-side.

---

## P1 — Payment signature leaks into URL, history, and Referer

The hosted-page flow returns `razorpay_payment_id` / `razorpay_signature` in the query string; `Billing.tsx:88-101` and `SubscriptionGate.tsx:79-92` read them from `window.location.search`. Before `replaceState` runs (which happens only in the mutation's `onSuccess`), those values are in browser history, in the `Referer` header of every subresource the page loads, and in any CDN/analytics log.

**Fix:** call `window.history.replaceState` *immediately* on read, before firing the mutation. Longer term, use `callback_method: "post"`, or exchange the result server-side via a one-time nonce.

---

## P1 — `verify_and_activate` never confirms the payment actually succeeded

`subscription_manager.py:152-169`: it validates the signature, then sets `status = active`. But a valid signature only proves the `(payment_id, subscription_id)` pair was signed with your key — **it does not prove the payment was captured, nor that the amount or currency matched.**

**Fix:** after the signature check, call `fetch_subscription(subscription_id)` and require `status in ("authenticated", "active")`; fetch the payment and require `status == "captured"` and `amount` matching the plan, before activating.

---

## P1 — `verify_payment_signature` swallows every exception

`razorpay_client.py:174` — `except Exception:` catches the `RuntimeError("Razorpay is not configured")` raised by `_module()` and silently falls through to a manual HMAC. Config errors get masked as signature logic.

**Fix:** catch `razorpay.errors.SignatureVerificationError` only; let everything else propagate.

---

## P1 — Webhook status ordering bug

`handle_razorpay_event` sets `row.status` from `sub_entity["status"]` at lines 202-204, then **unconditionally overwrites it** at lines 213-219 based on event type. A `halted` subscription that emits `subscription.charged` lands as `active`. Similarly `payment.captured` blanket-activates without checking amount or billing cycle.

**Fix:** make the event-type branch respect the entity status — treat the entity as the source of truth and use the event type only to disambiguate. Verify the payment amount against the plan before activating.

---

## P1 — No webhook ordering guard

Razorpay retries and delivers out of order. `webhook_replay.py` gives replay/dedupe, but nothing prevents a late `subscription.activated` from resurrecting a subscription that was subsequently cancelled.

**Fix:** persist the last-applied event timestamp per subscription; drop events older than it.

Related, lower severity: dedupe **no-ops when Redis is absent** (`webhook_replay.py:70-71`, documented as fail-open). Freshness is still enforced, so this is a reasonable tradeoff — but it means the degraded state silently loses dedupe. Worth an alert.

---

## P2 — Correctness and hygiene

| # | Issue | Location |
|---|---|---|
| 1 | `_notify()` publishes the realtime `subscription.updated` event **inside** the transaction. If the commit fails, clients were already told it succeeded. Move to an after-commit hook. | `subscription_manager.py:116,139,175` |
| 2 | `total_count = 120` is applied regardless of interval — yearly plans request **120 years** of cycles. Derive from `plan.billing_interval`. | `razorpay_client.py:111` |
| 3 | `verify_and_activate` hardcodes a 30-day period extension for annual plans too. | `subscription_manager.py:171-173` |
| 4 | `_active()` compares an enum column against raw strings. Works by coincidence of value naming; use `SubscriptionStatus.*` members. | `subscription_manager.py:239` |
| 5 | **No plan-change path.** The UI says "Switch to this plan" but calls `startSubscription`, which creates a *second* subscription — no proration, no cancellation of the old one. Copy and behaviour disagree. | `Billing.tsx:304` |
| 6 | `base_price_cents` is never reconciled against the actual Razorpay plan amount. Your UI price and the charged amount can diverge silently. Add a startup reconciliation check. | — |
| 7 | `/billing/config` is unauthenticated. `key_id` is publishable so this is minor, but it also discloses whether billing is configured. | `billing.py:45` |
| 8 | Enterprise contact form uses `mailto:` and shows a success toast unconditionally — fails silently where no mail client is configured. | `SubscriptionGate.tsx:208-210` |

---

## UX / flow review

**The flow itself is sound** — plan select → email confirm → Razorpay modal (with hosted-page fallback) → verify → unlock is the right shape. The problems are in the edge states.

1. **Worst one: a failed payment shows a success toast.** If `loadRazorpayScript()` fails *and* `short_url` is null, both callers fall through to `toast.success("Subscription activated successfully!")` (`SubscriptionGate.tsx:126`, `Billing.tsx:134`). Given the P0 above, this is exactly what a user sees today. It should be an error state.
2. **No pending state during SDK load.** `subscribe.isPending` covers the API call but not `loadRazorpayScript()`'s network fetch — dead air between click and modal.
3. **`onDismiss` is never passed** by either caller (`razorpay.ts` supports it). Closing the Razorpay modal leaves an `incomplete` subscription with no feedback and no retry affordance.
4. **No recovery path when verify fails after a successful charge.** The user has been charged, sees a red toast, and has nowhere to go. Needs an explicit "payment received, activation pending — we'll email you / contact support" state.
5. **Two sources of truth for pricing.** `SubscriptionGate.tsx` hardcodes ₹4,995 / ₹14,995 / SKU counts in JSX; `Billing.tsx` reads them from `/billing/plans`. These will drift. Drive the gate from the API too.
6. **Inconsistent email defaults.** `SubscriptionGate` prefills the logged-in email; `Billing.tsx` starts empty and has no `required` or validation — you can submit blank and get a 422.
7. **Accessibility:** the used-trial card uses `opacity-60 pointer-events-none` (`SubscriptionGate.tsx:293`) — invisible to keyboard and screen-reader users. Use `disabled` + `aria-disabled`. The billing-cycle toggle is done well by contrast (proper `role="switch"` + `aria-checked`).
8. Visual design is genuinely good — hierarchy, the "Popular" treatment on Scale, and the usage meters with 80%/100% thresholds are all solid. "Save 16%" checks out (₹49,950 vs ₹59,940 = 16.7%).

---

## Test coverage

`backend/tests/test_billing.py` has three unit tests, all against fakes:
`test_razorpay_payment_signature_verification`, `test_subscription_manager_verify_and_activate_unit`, `test_handle_razorpay_webhook_events_unit`.

**There is no test for `start_subscription` at all** — which is precisely why the P0 shipped. Nothing exercises the `razorpay_plan_id is NULL` branch.

Minimum additions:
- `start_subscription` with a priced plan and NULL `razorpay_plan_id` ⇒ must raise, must not return `active`.
- `start_subscription` called twice ⇒ one subscription.
- `trial_days` supplied in the body ⇒ ignored / rejected.
- Webhook: `halted` entity + `subscription.charged` event ⇒ must not become `active`.
- Webhook: out-of-order `activated` after `cancelled` ⇒ stays cancelled.
- `verify_and_activate` where Razorpay reports the payment as failed ⇒ must not activate.
- E2E (`frontend/e2e/billing.spec.ts`): Razorpay test-mode card through the full flow.

---

## What's needed to be production-ready

**Config / infra**
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` in `.env` **and** `.env.example`.
- Run `scripts/sync_razorpay_plans.py` to backfill `razorpay_plan_id`.
- Register the webhook endpoint in the Razorpay dashboard; subscribe to `subscription.*`, `payment.captured`, `payment.failed`.
- Redis available in prod so webhook dedupe is actually active.
- `APP_BASE_URL` setting for server-constructed callback URLs.

**APIs that don't exist yet and are needed**
- `POST /billing/subscription/change` — plan upgrade/downgrade with proration.
- `GET /billing/invoices` + `GET /billing/invoices/{id}` — customers will ask for these on day one.
- `POST /billing/subscription/resume` — un-cancel before period end.
- `GET /billing/payment-methods` — currently no way to see or update a card.
- Refund handling (`refund.created` / `refund.processed` webhooks are unhandled).
- Dunning: `payment.failed` sets `past_due` but nothing notifies the customer.

**Observability**
- Alert on `billing.razorpay.unknown_subscription` (currently only a warning log).
- Metric on verify-failure rate — the signal for a broken checkout.
- Daily reconciliation job: local `Subscription` rows vs Razorpay's list.

---

## Suggested order

1. P0 #1 — block activation for priced plans without `razorpay_plan_id`. **Today.**
2. P0 #2, #3 — server-derived `trial_days`, idempotency guard.
3. P1 #1, #2 — `redirect_url` allowlist, signature out of the URL.
4. P1 #3 — confirm payment with Razorpay before activating.
5. The failed-payment-shows-success toast (UX #1) — one-line fix, high blast radius.
6. Tests for everything above, then the remaining P1s.
7. P2s and the missing APIs.
