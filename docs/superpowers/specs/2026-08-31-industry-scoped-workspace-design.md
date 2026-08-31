# Industry-scoped workspace model

**Date:** 2026-08-31
**Status:** Approved (design), pending implementation
**Author:** Claude Code, via `superpowers:brainstorming`

---

## 1. Problem

SANKET is technically multi-tenant and must stay that way: every company's data
is isolated by PostgreSQL row-level security. But "multi-tenant" has been doing
double duty — as a security property *and* as a customer-facing feature — and a
second, unrelated idea got tangled into it: every new workspace is provisioned
with access to **all five industries** and a UI switcher to move between them.

That is wrong on two counts.

**Product.** A fashion retailer does not want a pharma GxP module in their
sidebar. The switcher advertises capability the customer neither bought nor
needs, and it makes every screen answer "which industry are we pretending to be
right now?" instead of "what should I reorder?".

**Security.** The industry boundary is not enforced anywhere on the server.
`backend/app/routers/industries/fashion.py:21` accepts `ctx: ActiveIndustry`
and then hardcodes `IndustryCode.fashion` in every query without ever comparing
the two. The same holds for electronics, pharma, agrocenter and hardware. The
only industry gate that exists is the `X-Industry-Code` check in
`backend/app/middleware/tenant_context.py:114-138`, and it validates against
the token's `industries` claim — which both signup paths
(`routers/auth.py:517`, `:688`) populate with all five codes. So today any
authenticated tenant can call any industry's endpoints and get a 200.

RLS still scopes those responses to the caller's own tenant, so this is not a
cross-tenant data leak. It is a missing authorization boundary, and it is the
core of what this work fixes.

## 2. The invariant

Two boundaries, kept strictly separate. They are different questions and they
get different mechanisms.

| Question | Mechanism | Change |
|---|---|---|
| Whose company data may this user read? | PostgreSQL RLS, tenant-scoped sessions | **None.** Untouched, still tested. |
| Which product modules may this company access? | `tenants.industry` — one value, immutable after onboarding | New, enforced in one place. |

Every customer tenant has **exactly one** authoritative industry. Every member
inherits it. No authenticated user can see, select, or reach another one.

## 3. Central authorization primitive

New module `backend/app/core/industry_scope.py`:

- `TenantIndustry` — FastAPI dependency returning the tenant's `IndustryCode`.
- `require_industry(code)` — dependency factory applied at
  `app.include_router(...)`, mirroring the existing `gated` entitlement pattern
  documented at `backend/app/main.py:417-421`. Returns 403 unless the tenant's
  industry equals `code`.
- `assert_industry(requested, tenant_industry)` — for client-supplied industry
  values in request bodies and form fields (integrations); raises 403 on
  mismatch.

Applying the gate at router registration rather than per-endpoint is deliberate
and follows the precedent already set by the subscription paywall: a new
endpoint inherits the gate by construction, so an endpoint author cannot forget
it because they never write it.

## 4. Data model

### 4.1 End state

One authority: `tenants.industry` (renamed from `tenants.active_industry`, so
no data moves and every existing tenant keeps the value it already had).

`tenants.industries` and `users.active_industry` survive as **database-maintained
mirrors**, not as fields any code may write or read:

- `CHECK (industries = ARRAY[industry]::industry_code[])` on `tenants`.
- `BEFORE INSERT OR UPDATE` trigger on `tenants` setting
  `industries := ARRAY[NEW.industry]`.
- `BEFORE INSERT OR UPDATE` trigger on `users` setting
  `active_industry := (SELECT industry FROM tenants WHERE id = NEW.tenant_id)`.

Both triggers are `SECURITY DEFINER` with a pinned `search_path`. The users
trigger reads `tenants`, which RLS would otherwise block on a cross-tenant
insert. This is trigger-level privilege inside a migration, not application
code opening a superuser connection, so the AGENTS.md section 6 rule holds.

Because the triggers own both columns, **`Tenant.industries` and
`User.active_industry` are removed from the SQLAlchemy models entirely.** There
is exactly one authoritative field; any code still reading the old attributes
fails loudly at attribute access rather than silently reading stale data.
Dropping the columns themselves is a documented follow-up migration, not this
one.

### 4.2 Migration `0020_industry_scoped_workspace`

Forward, one transaction:

1. `ALTER TABLE tenants RENAME COLUMN active_industry TO industry`
2. Snapshot each tenant's existing array into `settings['legacy_industries']`
3. `UPDATE tenants SET industries = ARRAY[industry]::industry_code[]`
4. Add `ck_tenants_single_industry`
5. `UPDATE users u SET active_industry = t.industry FROM tenants t WHERE u.tenant_id = t.id`
6. Create both trigger functions and triggers
7. Create the dedicated `sandbox` tenant + viewer user (see section 7)

Guarantees:

- **Deterministic.** Every existing tenant keeps its current `active_industry`.
  That column is `NOT NULL`, so there is no ambiguous case.
- **Non-destructive.** The original industry arrays are preserved in
  `settings['legacy_industries']`. `industry_profiles` rows for unselected
  industries are preserved and simply become unreachable.
- **Reversible.** Downgrade restores the arrays from the snapshot, drops the
  constraint and triggers, and renames the column back.
- **RLS untouched.** No policy is added, dropped or altered.

## 5. Authentication and claims

- `SignUpRequest.industry: IndustryCode` and
  `GoogleSignUpRequest.industry: IndustryCode`, both **required**. Validation
  comes from the canonical `app.models.enums.IndustryCode`, so an invalid code
  is a 422 and no frontend-only list can drift.
- Both signup paths create the tenant with the chosen industry and seed
  **one** `IndustryProfile`, not five.
- The **`industries` claim is removed** from `mint_dev_token`,
  `set_user_claims`, `FirebaseVerifier._normalize`, the sandbox session, and
  `app/scripts/seed_firebase_users.py`. Tokens carry exactly one `ind`.
- `/auth/session` claim-staleness comparison is against **`tenant.industry`**,
  never the user row.
- `X-Industry-Code` no longer switches anything:
  - unknown code → 400 (unchanged)
  - known code that is not the tenant's → **403**
  - matching code → pass through

  Old clients fail closed.
- Invitations accept no industry (`InviteCreate` already has none — this is now
  a tested invariant rather than an accident).

### 5.1 Trust model

`ind` in the token stays the request-time source, minted from the tenant row at
every provisioning path. Because industry is immutable once locked, the claim
cannot drift after onboarding.

During the correction window the claim *can* go stale, so the correction
endpoint updates the tenant, re-mints the dev token, sets new Firebase custom
claims, **and revokes the user's Firebase refresh tokens** so an old `ind`
cannot be replayed for the rest of its ~1h life.

Lock-state checks always read the database. A JWT claim is never consulted to
decide whether the industry may still be changed.

### 5.2 Industry correction window

`POST /industry/activate` is re-scoped from "switch industry" to "correct the
industry during initial setup". Owner/admin only. Returns **409 Conflict** when
either is true:

- onboarding status is `complete`, or
- the tenant has real data: any row in `products`, `skus`, `historical_sales`,
  or any integration connection record.

### 5.3 Invite acceptance (new)

`POST /auth/accept-invite` — public endpoint, because the invitee has no bearer
yet. `backend/app/routers/invites.py:135` already mints a link to
`/accept-invite?token=...` and nothing has ever redeemed it.

- constant-time comparison against the stored token hash
- expiry and single-use enforced; seat limit re-checked at redemption
- creates the user in the **invite's** tenant with the **invite's** role
- provisions Firebase (or dev password) credentials and mints claims from the
  tenant's industry
- **accepts no industry and no role from the client**

## 6. Backend authorization

- The five industry routers are registered with
  `dependencies=gated + [require_industry(<code>)]`. Direct URL or API access
  to another industry returns 403 regardless of what the frontend renders.
- `GET /industry/available` (enumerates all five to an authenticated caller) is
  replaced by a **public** `GET /industry/catalog` used by the signup form and
  the marketing site. Public prospects may browse every vertical; authenticated
  users see only their own.
- `backend/app/routers/cross_industry.py` and the unrouted
  `frontend/src/pages/CrossIndustryCorrelation.tsx` are **deleted**. A
  permanently-403 endpoint is worse than no endpoint, and today's
  cross-industry code must not stay exposed for a hypothetical future plan.
  Recorded as future work in section 10.
- Integrations: `target_industry` in `ConnectRequest`, the SQL-source request
  and the upload form becomes optional-and-verified. Supplied and mismatched →
  403. The server always persists the tenant's industry.
- Background and offline paths updated to the single tenant industry:
  `app/workers/whatsapp_digest.py:85`, `ml/scripts/train_all.py:50-57`,
  `ml/scripts/backfill_features.py:33-43`.

## 7. Sandbox

The public sandbox currently signs anonymous internet visitors into
`sanket-dev` (`config.py:114`) — the shared development tenant, which is also
where non-production `/auth/session` auto-provisions unknown Google users. The
landing page's industry picker is cosmetic: `launchSandbox` only calls
`setIndustry(code)` client-side, backed by the `X-Industry-Code` header this
work removes.

A dedicated `sandbox` tenant is created by migration, pinned to Fashion, with
its own `viewer` user. The cosmetic picker is removed and the CTA reads as a
Fashion sample workspace.

Per-industry sandbox tenants are explicitly **out of scope**: no demo-data
generator exists in the repository, so five sandboxes would start empty unless
this phase also built sample-data seeding for five verticals. Recorded in
section 10.

## 8. Frontend

- `stores/industry.ts` becomes a **read-only projection of the verified
  session**: `persist` removed, `setIndustry` removed, the sole writer is
  called from `auth.setSession`. Around 40 existing call sites keep compiling
  while switching becomes impossible. Bootstrap deletes the legacy
  `sanket.industry` localStorage key so stale persisted state cannot win.
- `api/client.ts` stops sending `X-Industry-Code`.
- `components/layout/IndustrySwitcher.tsx` deleted, along with its use at
  `TopBar.tsx:193`.
- `Login.tsx` gains a required industry selector on the sign-up form and in the
  Google workspace modal, fed by `/industry/catalog`.
- `LandingPage.tsx` exposes four unambiguous entry points: **Try Live
  Sandbox**, **Create Workspace**, **Request Enterprise Demo**, **Sign In**.
- `onboarding/StepIndustry.tsx` becomes confirm-and-correct rather than select,
  rendering as locked (no control) when locked or when the viewer is not
  owner/admin — so invited members never see a selection step. The step key is
  kept so persisted onboarding state needs no migration.
- Route guards on industry-specific routes (`pharma/batches`) render a clear
  access-denied page; `Sidebar.tsx` hides non-applicable modules. Industry now
  arrives on the same session object the existing `auth.ready` guard already
  waits for, so no independent state remains that could flash.
- `Integrations.tsx` loses its target-industry selector.
- New `/accept-invite` page.
- Icons only via `frontend/src/components/ui/icons.tsx` (AGENTS.md section 6).

## 9. Marketing and positioning

Multi-tenancy stops being a customer-facing differentiator. Replacement
positioning: *"One focused planning workspace, configured for your industry
from day one."*

**Kept, because it is accurate security architecture:** the RLS and
tenant-isolation material in `docs/SECURITY_AND_COMPLIANCE_REVIEW.md`, the
`README.md` architecture diagram, and the landing page's security section.

**Changed:** product descriptions that imply one workspace roams freely across
industries — `CLAUDE.md:18` ("multi-tenant, multi-industry SaaS"), landing-page
positioning copy. Public prospects may still browse all five verticals.

## 10. Future work — deliberately not built

- **Separate workspaces per industry.** A customer wanting two industries
  creates two workspaces. No code needed.
- **Purchased multi-industry entitlements.** If an enterprise plan ever sells
  this, it goes through the existing `subscriptions` entitlement architecture.
  No entitlement framework is added now, and no switching code is left exposed
  against that possibility.
- **Per-industry sandboxes** with seeded sample data (section 7).
- **Cross-industry shortage correlation** (section 6) — deleted, recoverable
  from git history.
- **Dropping `tenants.industries` and `users.active_industry`** columns, once a
  release has passed with the triggers in place (section 4.1).

## 11. Acceptance criteria

- A new workspace cannot exist with access to every industry by default.
- Every customer tenant has exactly one authoritative industry.
- All tenant members inherit it.
- Authenticated users cannot see or switch to another industry.
- Direct URLs, headers and API calls cannot bypass the restriction.
- Integration requests cannot send data into another industry.
- Cross-tenant RLS isolation remains intact and tested.
- Sandbox, Create Workspace, Enterprise Demo and Sign In are all clear public
  entry points.
- Multi-tenancy is no longer marketed as the USP; tenant isolation remains
  documented as security architecture.
- Migrations preserve existing data.

## 12. Known constraint

`backend/tests/conftest.py` builds its database with testcontainers. Docker
must be running to observe a failing backend test. There is no PostgreSQL on
`:5432` as a fallback.
