# Handoff Prompt — SANKET / Prisma Audit Continuation

**Paste everything below the line into a fresh Claude Opus session that has access
to `C:\Users\admin\Desktop\Prisma`.**

---

You are picking up a senior-level product and engineering audit of **SANKET**
(repo folder name: `Prisma`), a multi-tenant, multi-industry predictive analytics
and supply-chain SaaS. Act as Product Owner, Project Manager, Business Analyst,
UX/UI Designer, Software Architect, Engineer, DevOps, and QA — the same composite
role the previous run held.

A previous agent completed Phases 0 through 4 of a five-phase brief. **Read the
existing deliverables before doing anything else.** Do not redo the work. Your job
is to verify, extend, and act on it.

---

## 1. Read these first, in this order

| File | What it is |
|---|---|
| `docs/audit/00-open-questions.md` | Open questions, 4 resolved, ~8 still open |
| `docs/audit/01-codebase-map.md` | Full static map: stack, multi-tenancy, features, auth, billing, data model, configurability, tests/CI |
| `docs/audit/02-product-walkthrough.md` | Live UI walkthrough. 5 P0s, 9 P1s, 8 P2s with repro steps and file:line causes |
| `docs/audit/03-state-of-the-product.md` | Readiness grades, liabilities, top 10 fixes with effort estimates |
| `docs/strategy/customization-summary.md` | Three-minute executive summary of the customization strategy |
| `docs/strategy/customization-plan.md` | The main deliverable: architecture, 5 industry templates, build plan |
| `CLAUDE.md` | Project conventions + the gstack section |
| `PAYMENT_AUDIT.md`, `PAYMENT_REVIEW_ROUND2.md` | Two earlier payment reviews (2026-07-21), repo root |

---

## 2. The situation in one paragraph

The infrastructure is genuinely strong: PostgreSQL row-level security with
`FORCE ROW LEVEL SECURITY`, a boot-time assertion that refuses to start in
production if the DB role can bypass isolation, replay-protected Razorpay
webhooks, fail-closed RBAC with a live DB re-check, automated partition
maintenance, seven CI workflows. The product surface is not finished. You cannot
take money, the paywall is a React component with no server enforcement behind it,
a tenant who completes onboarding is thrown back to step one, and a tenant who
selects Pharmaceuticals is served the Apparel archetype while the UI displays a
`21 CFR PART 11` badge. The gap between engineering quality and product
completeness is the story of this codebase.

---

## 3. The most important open item

**462 lines of payment security fixes are uncommitted in the working tree.**

```
git log --oneline -1
  → 65023e1 feat: rebrand project assets to Sanket, ...

git show HEAD:backend/app/routers/billing.py | grep trial_days
  → 27:    trial_days: int | None = Field(default=14, ge=0, le=60)     # vulnerable

git diff --stat -- backend/app/routers/billing.py \
                   backend/app/services/billing/subscription_manager.py
  → 462 insertions(+), 29 deletions(-)
```

`HEAD` still contains the caller-supplied `trial_days` hole. `.github/workflows/build-images.yml`
builds from the **committed** tree, so these fixes cannot reach staging or
production regardless of how many deploys run. Restarting the backend is not
sufficient — the work must be committed.

There are also uncommitted changes in ~20 other files (models, connectors,
frontend) that nobody has reviewed. Do not commit wholesale without reading them.

**Ask the user whether they have committed this before you re-test anything.**
If they have, re-run the P0 verification in §6 — several findings may now be stale.

---

## 4. Environment and tooling constraints (learned the hard way)

- **App runs on the user's machine**, not in your sandbox. Frontend
  `http://localhost:5173`, backend `http://localhost:8000`. The SPA proxies
  `/api/*` to `127.0.0.1:8000` via `vite.config.ts:13-18`.
- **Your bash sandbox cannot reach their localhost.** Use the Claude-in-Chrome MCP
  (`mcp__claude-in-chrome__*`) for anything touching the running app. `/browse`
  from gstack will not work for the same reason.
- **gstack is not installed as slash commands.** The skills directory is read-only
  from the sandbox, `bun` is unavailable, and terminals on the user's Windows
  machine are tier-"click" so you cannot type into them. The previous agent cloned
  gstack and followed the skill files by hand. Do the same: clone
  `https://github.com/garrytan/gstack.git` to a scratch dir and read
  `office-hours/SKILL.md`, `plan-ceo-review/SKILL.md`, `qa/SKILL.md`,
  `investigate/SKILL.md`.
- **Path mapping**: workspace `C:\Users\admin\Desktop\Prisma` is
  `/sessions/<session>/mnt/Prisma/` in bash.
- **Bash times out at 45s.** Avoid recursive greps over `frontend/node_modules`.
- **Razorpay keys are blank.** `/billing/config` returns `configured: false`. No
  live checkout, no test cards, no 3DS. Provider is mocked/stubbed by agreement.

### Useful probing recipe

The previous agent probed the API from inside the page context. This works:

```js
// via mcp__claude-in-chrome__javascript_tool on a localhost:5173 tab
const tok = localStorage.getItem('sanket.dev.token');
const H = {'Authorization': 'Bearer ' + tok};
const r = await fetch('/api/v1/products', {headers: H});
```

Notes: use the **relative** `/api/v1` path, not `localhost:8000` directly.
`sanket.dev.token` works; the `access_token` inside `sanket.dev.session` returns
401 (that is finding P1-9). Do not use `return` at top level in
`javascript_tool` — it throws.

### Test tenants already created

| Email | Password | Tenant ID | Industry chosen |
|---|---|---|---|
| `qa-alpha@example.com` | `QaAudit!2026x` | `53c83b38-5766-4e02-8dbe-a408d42025cf` | Pharmaceuticals |
| `qa-gamma@example.com` | `QaAudit!2026z` | `d632cfe9-6833-4ba2-aafa-648c05d86ff8` | (not onboarded) |

Also `qa-beta@example.com` and `leak-probe@example.com` exist from probes. Signup
lives at `/login?mode=signup` — `/signup` is a 404.

---

## 5. Findings inventory (verify, do not re-derive)

### P0 — ship-blocking

1. **No server-side entitlement.** The paywall is `SubscriptionGate.tsx:36`, a
   React component. `grep -rn "require_subscription\|entitle" backend/app/` returns
   only comments. With zero subscription, `/products`, `/skus`,
   `/inventory/levels`, `/signals`, `/alerts`, `/webhooks/endpoints`,
   `/financial/impact`, `/billing/usage` all return **200**.
2. **`GET /billing/plans` returns 500**, as does `POST /billing/subscription`.
   Every paywall button is dead. Cause unconfirmed — **get the server traceback.**
3. **Onboarding completion is not persisted client-side.** `OnboardingGate.tsx:12`
   reads `useAuthStore(s => s.onboarding)`, hydrated from the `sanket.dev.session`
   localStorage blob written once at signup. Server returns
   `{"status":"complete"}` but the SPA bounces the tenant to `/onboarding` step 1
   forever.
4. **Industry selection never applied.** JWT `ind` claim stays `fashion` after
   signup and is never reissued. A pharma tenant gets 26-week horizon instead of
   52, fashion signals, fashion feature flags, standard audit instead of GxP —
   while the UI shows `GXP · 21 CFR PART 11`. Same root cause as #3.
5. **Signup echoes the submitted password in plaintext** in its 422 body via
   FastAPI's default `RequestValidationError` handler (`detail[].input`).

### P1 (nine)

Plan changes not implemented (`subscription_manager.py:113`); cancel-at-period-end
blocks resubscribe (`:219`); abandoned checkout burns the trial (`:480`);
`/billing/portal` has no RBAC (`billing.py:251`); "Select Growth" silently grants a
trial (`0017_billing_p0_guards.py:66` + `SubscriptionGate.tsx:380,422`); prices
hardcoded in JSX (`:402,447`); onboarding ignores industry horizon
(`StepCalendar.tsx:53` hardcodes 13 vs `StepIndustry.tsx:109`); validation errors
render under the wrong field; signup's returned `access_token` does not
authenticate.

### P2 (eight)

`/signup` 404s; landing-page skeleton stall; onboarding transition shows stale
step body; "Forecast engine ready" pip stays green after failure; workspace slug
asked before anything a customer recognises; industry not asked at signup;
"30+ sources" claim vs four implemented connectors (Amazon FBA does not exist);
"1/5 seats used" before any subscription.

### What is genuinely good — do not "fix" these

Tenant isolation is correct by construction. No endpoint accepts a caller-supplied
`tenant_id`; every route derives it from `request.state` via the `TenantId`
dependency (`industry_router.py:66`). RLS + FORCE RLS + the boot assertion
(`database.py:116-175`) close the classic footguns. `X-Industry-Code` switching is
deny-by-default and correctly validated (`tenant_context.py:114-138`). The billing
**source** handles capture confirmation, amount matching, subscription-ownership
checks, webhook replay protection, event ordering, and post-commit notification
flushing correctly.

---

## 6. What to do next

**Phase 5 was never defined in the original brief. These are the recommended next
steps, in order. Confirm with the user before starting.**

1. **Confirm the commit status of the 462-line diff (§3).** If committed and
   deployed, re-verify every P0 in §5 and update `02` and `03`. Several may be
   fixed. If not committed, that is the top priority and everything else waits.
2. **Get the `/billing/plans` 500 traceback** from the backend log. This is the
   single unblocking action for all payment testing.
3. **Re-run the live cross-tenant isolation test**, which was blocked by P1-9.
   Static analysis found no injection surface, but it should be confirmed
   empirically once a second tenant's token works.
4. **Areas the previous run explicitly did not assess** — say so rather than
   letting silence read as approval:
   - The ML stack (`backend/ml/`), model quality, forecast accuracy
   - Performance and load behaviour (no load test exists)
   - WebSocket realtime layer under concurrency
   - The 11 external signal connectors against live APIs
   - Accessibility (no WCAG pass; a `design:accessibility-review` skill exists)
5. **If the user wants implementation**, start with `03`'s top 10 in order. Items
   1-5 are roughly one week agent-assisted and take the product from "unbuyable and
   free" to "can take money and enforces it."

---

## 7. Ground rules carried forward

- **Cite `path:line` for every claim about the codebase.** Verify line numbers
  before writing them — the previous run found two off-by-a-few citations on its
  verification pass and corrected them.
- **Label inference as inference.** Anything not directly verified is an
  `[ASSUMPTION]`, not a fact.
- **Distinguish [LIVE] from [SOURCE] findings.** The running build and the working
  tree are different code. This distinction is load-bearing in `02`.
- **Keep `docs/audit/00-open-questions.md` current.** Add anything you need from
  the user.
- **Do not write application code or open PRs unless explicitly asked.** The
  previous run was analysis-only and touched nothing under `backend/`,
  `frontend/`, `infra/`, or `scripts/`.
- **Never use real payment cards or real personal data.** Test identities only.
- **Stop and ask** for credentials, OTP/2FA, or anything needing a real payment
  method.
- **Use the AskUserQuestion tool** for clarifying questions rather than asking in
  prose.

---

## 8. Open questions to put back to the user

Resolved already: the five industries are **Apparel & Fashion, Consumer
Electronics, Pharmaceuticals, Agro, Hardware**; the test environment is
`localhost:5173`; gstack is manual-method-only; Razorpay is mocked.

Still open — ask these:

1. **Has the 462-line payment diff been committed and deployed?** (blocking)
2. **Razorpay test keys**, or confirm payments stay code-review-only? (blocking)
3. **Do you have a customer, pipeline, or pilot in any of the five verticals?**
   This overrides the plan's recommendation to build Apparel first.
4. Is GST / Indian tax handling in scope? Prices are ₹-denominated with no tax
   logic anywhere.
5. Which is authoritative for entitlement, `tenants.tier` or
   `subscriptions.plan_id`? Both exist and nothing reconciles them.
6. Is the connector catalogue (Kafka, Snowflake, AWS, Amazon FBA) aspirational?
   Only four connectors are implemented.
7. Who owns plan pricing — the JSX literals, `plans.base_price_cents`, or the
   Razorpay dashboard? Three sources of truth today.
8. `backend/test_venv/` is a committed virtualenv. Remove it?
9. Should the ~20 other uncommitted files be reviewed before committing?

---

## 9. The customization strategy, in brief

So you do not contradict it. Full reasoning in `docs/strategy/customization-plan.md`.

The previous run put the brief through the gstack office-hours six questions and
the CEO review, and the pushback changed the plan:

- **Eleven axes reduced to four in v1** (terminology, custom fields, branding,
  dashboard layout), three in v2 (workflow labels, role templates, notification
  templates), four deferred with stated triggers (custom objects, custom forms,
  scripting runtime, per-tenant integrations).
- **Five industry templates reduced to one first: Apparel & Fashion**, because
  Shopify and WooCommerce are the only two working integrations and pharma does not
  run on Shopify. Sequence: Apparel → Hardware → Electronics → Agro → Pharma.
- **Pharma is last, not second**, despite the highest contract value, because the
  `21 CFR PART 11` claim is currently false and needs e-signature on config
  changes, an ERP connector, and computer system validation.
- **A one-week money-path prerequisite gates all config work.**
- **Storage is JSONB + GIN, explicitly not EAV.** Config documents are immutable
  and versioned; rollback is an `is_published` pointer move; migration is
  migrate-on-read with lazy persistence; the resolver must never use
  `session_no_rls()`.
- **Office-hours Q1 has no answer.** There is no evidence any tenant wants
  customization. Phase 4 of the build plan is a design partner, not a launch, and
  the roadmap should be killable on that signal.

Do not quietly re-expand scope back to eleven axes and five templates. If you
think the reduction was wrong, argue it explicitly with evidence.
