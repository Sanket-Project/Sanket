# SANKET platform admin console

**Date:** 2026-09-10
**Status:** Approved (design), pending implementation
**Author:** Claude Code, via `superpowers:brainstorming`
**Branch:** `feat/platform-admin-console` (from `2227fb3`)

---

## 1. Problem

SANKET has two kinds of people who need to act on customer workspaces, and the
codebase only knows about one of them.

Customers are modelled thoroughly: every identity is a user of exactly one
tenant, every request is scoped to that tenant by PostgreSQL RLS, and module
access is scoped to the tenant's one industry. What does not exist anywhere is
the *operator*: the SANKET staff member who creates a customer, invites their
first administrator, activates an enterprise contract, imports their history,
starts their first forecast, and later suspends them or investigates a failed
job. Today every one of those actions is either impossible or done with raw SQL
(`sql/011_dev_subscription.sql` is how the dev tenant got a live subscription).

This design adds an internal console at `/admin` for those operators, backed by
`/api/v1/admin/*`, without weakening the customer boundary.

## 2. Invariants

Three boundaries, each with one mechanism. The console adds the third; it does
not touch the first two.

| Question | Mechanism | Change |
|---|---|---|
| Whose company data may this request read? | PostgreSQL RLS, `Database.session(tenant_id)` | **None** for customer paths. Admin per-tenant work also runs through it. |
| Which product modules may this company use? | `tenants.industry`, `core/industry_scope.py` | **None.** Admins follow the same lock rule. |
| May this person operate the platform? | `platform_admins`, checked in the DB on every admin request | **New.** |

1. A customer identity — any role, any tenant — can never reach an admin
   endpoint, and can never be granted a platform role, even by a stray SQL write.
2. Platform access never widens a customer API. Customer API behaviour is
   unchanged except for the deny-only suspended/archived checks (§6.4); logic
   shared with the console is extracted from customer routers without changing
   their responses (§8.2).
3. Every per-tenant admin read or write runs in a session scoped by RLS to the
   tenant named in the URL. Cross-tenant access exists only for directory and
   aggregate queries, and only through one wrapper that requires a verified
   platform principal.
4. Every platform action is audited in the same transaction as the action. If
   the audit write fails, the action fails.
5. Nothing on an admin screen is fabricated. A metric the database cannot
   support is shown as unavailable, not estimated.

## 3. Decisions taken during design

| Decision | Choice |
|---|---|
| Platform identity & data path | **Approach A:** operator tenant + DB-checked platform roles + tightly limited use of the existing RLS bypass. (Rejected: a separate read-only Postgres role — kept as an upgrade path; a separate identity system — duplicates auth and changes the customer middleware.) |
| Billing scope | Assign a plan, activate an enterprise contract (super admin), cancel now or at period end. Upgrade/downgrade = cancel then assign. **No new Razorpay money logic.** |
| Support access | Tenant metadata is always visible to platform roles; customer *data* requires a time-limited, reason-bearing support session (§6.5). |
| Branching | Pre-existing uncommitted work committed separately as `2227fb3`; this work branches from it so migration `0022` chains after `0021`. |

## 4. What exists and is reused

| Existing | Location | Used for |
|---|---|---|
| Token verification, request context | `core/firebase_auth.py`, `middleware/tenant_context.py` | Authenticating operators exactly like customers |
| Tenant-scoped sessions / bypass session | `core/database.py:70`, `:92` | Per-tenant admin work / cross-tenant directory queries |
| Workspace creation | `services/workspace.create_tenant` | "Create customer" |
| Industry lock rule | `routers/industry_router._lock_reason` | Admin industry correction |
| Effective industry config | `services/industry_config.resolve_effective_config` | Defaults step, Industry tab |
| Billing engine | `services/billing/subscription_manager.SubscriptionManager` | Every admin billing action |
| Entitlement predicate | `core/entitlement.require_active_subscription` | Entitlement status shown in the console |
| Onboarding readiness | `services/onboarding_readiness.readiness` | Onboarding checklist |
| Invites | `routers/invites.py`, `routers/auth.accept_invite` | Customer administrator invite |
| File import + data quality | `services/integrations/file_import.py`, `services/data_quality_audit.py` | Import on behalf, validation results |
| Forecast job | `workers/forecast_worker.run_hybrid_forecast`, `services/hybrid_forecast.execute_hybrid_run` | Initial forecast, retry |
| Usage meters | `services/usage.py`, `usage_events` | API activity |
| Audit log | `audit_log` (append-only by RULE) | Tenant-visible mirror of platform actions |
| UI kit | `components/ui/*` (Table, Modal, ConfirmDialog, Badge, Card, Stepper, EmptyState, Skeleton, FileDropzone), `icons.tsx` | Every admin screen |

## 5. Gaps found in the audit, and how they are handled

1. **Every identity is tenant-bound.** Tokens must carry `puid/tid/role/ind`
   (`core/firebase_auth.py:259`). → Operators are users of a flagged operator
   tenant (§6.1).
2. **Cross-tenant access = `app.bypass_rls`.** Every policy is
   `bypass_rls() OR tenant_id = current_tenant_id()` (migration
   `64b00842a1e6`), and `sanket_app` can set that GUC. RLS protects against a
   forgotten `WHERE`, not against code that opts out. → Bypass confined to one
   wrapper (§6.3).
3. **Suspension does not stop live sessions.** `suspended` is checked only at
   `/auth/session`, dev-login, sandbox-session and accept-invite. → Deny-only
   check on gated routes + token revocation (§6.4).
4. **Industry change is locked by design** after setup completes or data
   arrives. → Admins get correction only while unlocked; no migration tooling.
5. **Plan changes unsupported** (`PlanChangeNotSupportedError`), and the
   zero-price `enterprise_monthly` plan creates an `incomplete` subscription
   that nothing can activate. → `activate_manual_contract()` (§7.4).
6. **Owners cannot be invited** (`schemas/invite.py: InviteRole`). → A
   platform-only owner invite; the customer endpoint is unchanged.
7. **No email delivery.** → The console shows the one-time link, labelled as
   not emailed.
8. **`max_skus` is enforced only on manual SKU creation** (`routers/skus.py:73`),
   not on imports or connectors. → Displayed honestly; enforcement unchanged.
9. **`audit.record()` fails open.** → A new fail-closed platform writer.
10. **Razorpay webhook events are not persisted.** → "Billing events" means
    subscription history plus platform billing actions.
11. **Only the `api_request` meter is ever recorded.** → SKU/seat/forecast/signal
    usage come from live counts.
12. **MFA is not enforced anywhere.** → Required for admin endpoints in
    production (§6.2).

## 6. Security model

### 6.1 Identity

- **Operator tenant.** `tenants.is_operator = true`; a partial unique index
  permits at most one. Slug from `PLATFORM_OPERATOR_TENANT_SLUG` (default
  `sanket-platform`). It is created by the bootstrap CLI, has no onboarding
  state and no subscription, never appears in admin listings or metrics, cannot
  be suspended or archived from the console, and signup can never create one
  (the slug is reserved and `create_tenant` never sets the flag).
- **Platform roles.** `platform_admins(user_id, role, is_active, granted_by)`.
  A `BEFORE INSERT OR UPDATE` trigger rejects any `user_id` whose tenant is not
  the operator tenant. Roles are deactivated, never deleted (no DELETE grant).
- **Bootstrap.** `backend/scripts/create_platform_admin.py` is the only way to
  create or deactivate a platform admin in this version. No API grants platform
  roles, so no request can escalate itself.
- **Operators sign in** with the normal mechanism (Firebase in production,
  dev-login locally) through the normal middleware. The operator tenant has no
  subscription, so the customer app shows them the paywall; the console lives
  on routes the paywall does not gate.

### 6.2 Per-request authorization

Every route under `/api/v1/admin` carries one router-level dependency, attached
once at `include_router` (the same "inherit it by construction" pattern as the
paywall and the industry gate):

1. `TenantContextMiddleware` has already verified the bearer.
2. One query loads the caller's `platform_admins` row joined to `users` and
   `tenants`. Required: platform row active, user active, tenant
   `is_operator`, tenant not suspended/cancelled. Otherwise **403** with a
   single generic message, and a best-effort `platform.access.denied` event.
3. **MFA.** `PLATFORM_ADMIN_REQUIRE_MFA` (unset = on in production, off
   elsewhere; explicit true/false overrides). When on, the verified Firebase
   token must carry `firebase.sign_in_second_factor`. The middleware carries
   that claim onto `request.state.auth_second_factor`. `GET /admin/me` answers
   with `mfa_satisfied: false` instead of 403 so the console can route an
   unenrolled operator to enrollment; every other endpoint returns 403.
4. **Permission.** Each endpoint declares one permission:

| Permission | support | admin | super_admin |
|---|:-:|:-:|:-:|
| `platform:read` — every open view | ✓ | ✓ | ✓ |
| `support:open` — open/end own support sessions | ✓ | ✓ | ✓ |
| `tenants:write` — create, edit, suspend, reactivate (from suspended), industry, profile, mark operational | | ✓ | ✓ |
| `users:write` — invite, revoke invite, role, enable/disable, revoke sessions | | ✓ | ✓ |
| `billing:write` — assign plan, cancel | | ✓ | ✓ |
| `data:write` — validate and import on a tenant's behalf | | ✓ | ✓ |
| `jobs:write` — trigger forecast, retry failed job | | ✓ | ✓ |
| `tenants:archive` — archive, unarchive | | | ✓ |
| `billing:contract` — activate enterprise contract | | | ✓ |

5. **Rate limiting.** `POST/PUT/PATCH/DELETE` under `/api/v1/admin/` use the
   heavy bucket (`rate_limit_heavy_per_minute`, per user). Reads use the normal
   per-user bucket.

Customer endpoints are untouched. An operator token used on a customer endpoint
is just a user of an empty workspace with no subscription.

### 6.3 Data access

- **Per-tenant** (every `/admin/tenants/{tenant_id}/...` endpoint): the handler
  first confirms the tenant exists and is not the operator tenant, then does all
  work in `db.session(str(tenant_id))`. RLS scopes every statement to that
  tenant, so a bug cannot return a second tenant's rows. Nested ids (users,
  invites, jobs) are resolved inside that session; an id belonging to another
  tenant is a **404**, never a 403 that confirms it exists. The operator tenant
  is refused by every per-tenant endpoint (404).
- **Tenant creation** is the one per-tenant write that cannot be scoped to its
  tenant before the tenant exists, and its slug check must see every tenant. It
  runs in the bypass session exactly as `/auth/signup` does today, and nothing
  else in that transaction reads or writes another tenant.
- **Cross-tenant** (dashboard, tenant list, search, users directory,
  subscriptions, usage, integrations, jobs, platform audit): only through
  `services/admin/data_access.platform_read(principal)`, which requires a
  `PlatformPrincipal` argument that only the authorization dependency can
  construct. It opens the transaction with `SET TRANSACTION READ ONLY` before
  setting the bypass GUC, so **the database refuses any write** made through it
  (via a `read_only` option added to `Database.session_no_rls`). Audit rows for
  reads (search, tenant view) are written in a separate transaction; if that
  write fails the request fails.
- **Column discipline.** Admin queries select named columns, and every response
  is a Pydantic model. These never leave the server: `users.password_hash`,
  `users.mfa_secret`, `users.firebase_uid`, `integration_connections.state`,
  `access_token_encrypted`, push-token hashes, `invites.token_hash`. A test
  serialises every admin response in the suite and asserts none of those field
  names or values appear.
- **Platform tables** (`platform_admins`, `platform_audit_events`,
  `support_access_sessions`): `ENABLE` + `FORCE ROW LEVEL SECURITY`, one policy
  `USING (bypass_rls()) WITH CHECK (bypass_rls())`. A customer (tenant-scoped)
  session can neither read nor write them.
- A `tenant_id` in an admin URL is a *selector chosen by an authorized
  operator*. It is never treated as an authority for anyone else.

### 6.4 Tenant lifecycle and enforcement

| Action | Transition | Permission | Side effects |
|---|---|---|---|
| Suspend | `trial`/`active` → `suspended` | `tenants:write` | Revoke every member's Firebase refresh tokens after commit |
| Reactivate | `suspended` → `active` | `tenants:write` | none |
| Archive | any → `cancelled` | `tenants:archive`, reason, typed slug | Revoke tokens |
| Unarchive | `cancelled` → `suspended` | `tenants:archive` | Then reactivate explicitly |

Enforcement (deny-only — it can only refuse, never grant, so `subscriptions`
stays the sole entitlement authority):

- `require_active_subscription` checks tenant status first and raises the
  existing `TenantSuspendedError` (402) for `suspended` or `cancelled`, before
  the subscription lookup and before the sandbox exemption.
- `/auth/session`, `/auth/dev-login`, `/auth/sandbox-session` and
  `/auth/accept-invite` refuse `cancelled` as they already refuse `suspended`.
  Nothing sets `cancelled` today, so no existing tenant changes behaviour.
- Revocation reaches Firebase-mode sessions within the revocation cache TTL
  (≤60 s). Dev tokens cannot be revoked and last ≤60 min; ungated setup routes
  (onboarding, planning, invites, billing, industry) remain reachable for that
  window. Documented limitation.

Suspension never touches the subscription or Razorpay.

### 6.5 Support sessions

- `POST /admin/tenants/{id}/support-sessions` with `reason` (≥10 chars) and
  `duration_minutes` (1 to `PLATFORM_SUPPORT_SESSION_MAX_MINUTES`, default and
  hard cap 120; the database also enforces `expires_at <= created_at + 2h`).
- Gated endpoints (🔒 in §7) require an unexpired, un-ended session **owned by
  the caller for that tenant**, checked on every request. Another operator's
  session, or a session for another tenant, does not count.
- Sessions unlock reads only. Writes are governed by permissions, never by a
  support session.
- Opening and ending a session are audited in both logs; the customer sees
  `platform.support_session.opened` with the reason and expiry in their own
  audit log.

### 6.6 Audit

- `services/admin/audit.record_platform_event()` inserts into
  `platform_audit_events` **in the caller's transaction** and does not swallow
  errors. A failed insert rolls back the action.
- For every **mutation** of a tenant and every support-session open/end, it also
  inserts into that tenant's `audit_log` (action `platform.*`, `user_id` =
  operator's user id, `new_value` carrying `actor_email`, `actor_role`,
  `reason` and action details), also fail-closed. Views and searches go to the
  platform log only.
- Failed actions (409/422/503 after authorization) are recorded with
  `outcome='failure'` in a separate best-effort transaction so attempts remain
  visible. Denied attempts are recorded best-effort with `outcome='denied'`.
- Audited: console sign-in (`POST /admin/session`), every mutation, support
  session open/end, search, tenant detail view, import, forecast trigger, retry.
- `platform_audit_events` is append-only: `no_update`/`no_delete` rules plus
  SELECT/INSERT-only grants, matching `audit_log`. Neither table's protections
  change.

Action names: `platform.console.sign_in`, `platform.access.denied`,
`platform.search`, `platform.tenant.{create,update,view,suspend,reactivate,archive,unarchive,industry_correct,profile_update,mark_operational}`,
`platform.invite.{create,revoke}`, `platform.user.{role_change,disable,enable,revoke_sessions}`,
`platform.subscription.{assign,activate_contract,cancel}`,
`platform.data.{validate,import}`, `platform.forecast.trigger`,
`platform.job.retry`, `platform.support_session.{open,end}`.

## 7. Data model — migration `0022` (after `0021`)

Additive and reversible.

| Change | Detail |
|---|---|
| `tenants.is_operator` | `BOOLEAN NOT NULL DEFAULT false`; `CREATE UNIQUE INDEX uq_tenants_single_operator ON tenants (is_operator) WHERE is_operator` |
| `platform_role` enum | `platform_super_admin`, `platform_admin`, `platform_support` |
| `platform_admins` | `id uuid pk`, `user_id uuid NOT NULL UNIQUE → users ON DELETE CASCADE`, `role platform_role NOT NULL`, `is_active bool NOT NULL DEFAULT true`, `granted_by uuid → users ON DELETE SET NULL`, `created_at`, `updated_at`; trigger `platform_admins_require_operator_user` (`SET search_path = pg_catalog, public, pg_temp`); grants SELECT, INSERT, UPDATE |
| `platform_audit_events` | `id bigserial pk`, `occurred_at timestamptz NOT NULL DEFAULT now()`, `actor_user_id uuid`, `actor_email citext`, `actor_role text`, `action text NOT NULL`, `target_type text NOT NULL`, `target_id text`, `tenant_id uuid`, `outcome text NOT NULL CHECK (outcome IN ('success','failure','denied'))`, `detail jsonb NOT NULL DEFAULT '{}'`, `ip_address inet`, `user_agent text`, `request_id text`; indexes on `(occurred_at DESC)`, `(tenant_id, occurred_at DESC)`, `(actor_user_id, occurred_at DESC)`, `(action, occurred_at DESC)`; `no_update`/`no_delete` rules; grants SELECT, INSERT, sequence USAGE |
| `support_access_sessions` | `id uuid pk`, `tenant_id uuid NOT NULL → tenants ON DELETE CASCADE`, `admin_user_id uuid NOT NULL → users`, `reason text NOT NULL CHECK (char_length(reason) >= 10)`, `created_at timestamptz NOT NULL DEFAULT now()`, `expires_at timestamptz NOT NULL CHECK (expires_at > created_at AND expires_at <= created_at + interval '2 hours')`, `ended_at timestamptz`, `ended_by uuid`; index `(tenant_id, admin_user_id, expires_at)`; grants SELECT, INSERT, UPDATE (`ended_at`, `ended_by`) |
| `hybrid_forecast_runs` | `trigger_source text NOT NULL DEFAULT 'customer' CHECK (IN ('customer','platform_admin','platform_retry'))`, `triggered_by uuid → users ON DELETE SET NULL`, `retry_of uuid → hybrid_forecast_runs ON DELETE SET NULL` |
| `invites.invitee_name` | `text NULL` — display only; acceptance still takes the name the invitee types |

RLS on the three platform tables as in §6.3. No existing policy is altered.

**No onboarding table.** Company profile lives in `tenants.settings.profile`
(`legal_name`, `company_identifier`, `primary_contact_name`,
`primary_contact_email`, `timezone` — IANA-validated). Region uses the existing
`tenants.home_region`. Limits use the enforced `max_skus` / `max_users`. The
customer-facing wizard state stays in `tenants.settings.onboarding`. The admin
checklist (§9) is computed from rows, never stored.

## 8. Backend

### 8.1 Layout

```
app/core/platform_authz.py        PlatformRole, PERMISSIONS, PlatformPrincipal,
                                  require_platform_admin (router dependency),
                                  require_permission(p), require_support_session,
                                  MFA evaluation
app/models/platform.py            PlatformAdmin, PlatformAuditEvent, SupportAccessSession
app/schemas/admin.py              every request/response model for /admin
app/services/admin/
    data_access.py                platform_read(principal) — the only bypass wrapper
    audit.py                      record_platform_event, mirror to tenant audit_log
    directory.py                  tenant list/filters/search, users directory
    metrics.py                    dashboard, notifications, usage aggregation
    lifecycle.py                  create/update/suspend/reactivate/archive, revocation fan-out
    users.py                      tenant user management
    billing.py                    admin billing actions over SubscriptionManager
    onboarding.py                 checklist derivation, mark operational
    data.py                       validate/import on behalf, data summary
    jobs.py                       job listing, trigger, retry
    support.py                    support sessions
    health.py                     component checks
app/routers/admin/                one module per area; __init__.py builds the
                                  /admin router with require_platform_admin attached
scripts/create_platform_admin.py  bootstrap / deactivate
```

### 8.2 Shared code extracted from existing routers

Behaviour of the existing endpoints does not change; their existing tests stay
as the proof.

1. `services/hybrid_forecast.enqueue_hybrid_run(...)` from
   `routers/hybrid_forecast.create_hybrid_run` (effective horizon, run row,
   arq enqueue, in-process fallback). Gains `trigger_source`, `triggered_by`,
   `retry_of`. The customer route passes `customer` and its user id.
2. `services/invites.create_invite(...)` from `routers/invites.create_invite`.
   The customer route still validates `InviteRole` (no owner); the platform
   service may pass `owner`.
3. `services/industry_correction.py`: `lock_reason()` and
   `correct_industry()` from `routers/industry_router` (DB update, member
   touch, claim sync, revocation). The customer route keeps its dev-token
   re-mint for the caller.
4. `core/entitlement.evaluate_entitlement(sub, now) -> EntitlementStatus`, a
   pure function the dependency and the console share; plus the deny-only
   status check (§6.4).
5. `services/integrations/upload.ingest_upload(...)` from
   `routers/integrations_hub.upload_file` (import, connection bookkeeping,
   audit) and a new dry-run `file_import.validate_rows(...)` using the same
   header map and row mappers: rows received, would accept, rejected (by reason:
   missing required field / invalid value), duplicate rows within the file,
   first 50 errors.
6. `SubscriptionManager.activate_manual_contract(session, *, tenant_id,
   period_end, reference, actor)` — the only billing-engine addition. Allowed
   only for the tenant's newest subscription when it is `incomplete`, its plan
   has `base_price_cents == 0` and no `razorpay_plan_id`, and `period_end` is in
   the future and ≤ 3 years out. Sets `active`, the period, and
   `metadata.contract = {reference, activated_by, activated_at}`.
7. `workers/forecast_worker.WorkerSettings.health_check_interval = 60`, so the
   arq health-check key is a real liveness signal.
8. `middleware/rate_limit._is_heavy(path, method)` gains the admin-write rule.
   `Database.session_no_rls(read_only=False)` gains the `read_only` option
   (existing callers unchanged).
9. `core/firebase_auth._normalize` surfaces `firebase.sign_in_second_factor`;
   `middleware/tenant_context` puts it on `request.state.auth_second_factor`.
10. `main.py` includes the admin router **without** the paywall dependency.

### 8.3 API — `/api/v1/admin`

🔒 = requires an active support session for that tenant (§6.5).
Lists are paginated (`page`, `page_size` ≤ 100) and return `total`.

| Area | Method & path | Permission |
|---|---|---|
| Session | `GET /me` — role, permissions, `mfa_required`, `mfa_satisfied` | platform role (MFA not required) |
| | `POST /session` — records console sign-in | `platform:read` |
| Dashboard | `GET /dashboard` · `GET /notifications` | `platform:read` |
| Search | `GET /search?q=` (≥2 chars; tenants by name/slug/id, users by email) | `platform:read` |
| Tenants | `GET /tenants?q&industry&status&subscription&onboarding&activity&health&sort` | `platform:read` |
| | `GET /tenants/slug-available?slug=` | `platform:read` |
| | `POST /tenants` · `PATCH /tenants/{id}` | `tenants:write` |
| | `GET /tenants/{id}` (overview; audited as a view) | `platform:read` |
| | `POST /tenants/{id}/suspend` · `/reactivate` | `tenants:write` |
| | `POST /tenants/{id}/archive` · `/unarchive` | `tenants:archive` |
| Industry | `PUT /tenants/{id}/industry` (409 when locked) | `tenants:write` |
| | `GET` / `PUT /tenants/{id}/industry-profile` | read / `tenants:write` |
| Onboarding | `GET /tenants/{id}/readiness` | `platform:read` |
| | `POST /tenants/{id}/onboarding/complete` | `tenants:write` |
| Users | `GET /users?q&tenant&role&status` (directory) | `platform:read` |
| | `GET /tenants/{id}/users` (members + pending invites) | `platform:read` |
| | `POST /tenants/{id}/invites` · `DELETE /tenants/{id}/invites/{iid}` | `users:write` |
| | `PATCH /tenants/{id}/users/{uid}` (role, is_active) | `users:write` |
| | `POST /tenants/{id}/users/{uid}/revoke-sessions` | `users:write` |
| | `GET /tenants/{id}/users/{uid}/activity` (`user.*` auth events only) | `platform:read` |
| Billing | `GET /plans` · `GET /subscriptions?status&plan&q` | `platform:read` |
| | `GET /tenants/{id}/subscription` (current, history, entitlement, quotas) | `platform:read` |
| | `POST /tenants/{id}/subscription` (assign) | `billing:write` |
| | `POST /tenants/{id}/subscription/cancel` | `billing:write` |
| | `POST /tenants/{id}/subscription/activate-contract` | `billing:contract` |
| Usage | `GET /usage?sort&near_limit` · `GET /tenants/{id}/usage` | `platform:read` |
| Data | `GET /tenants/{id}/data` (counts, date range, last import stats, DQ score) | `platform:read` |
| | `GET /tenants/{id}/data/quality` (findings with SKU codes) 🔒 | `platform:read` |
| | `POST /tenants/{id}/imports/analyze` · `/imports/validate` · `/imports` | `data:write` |
| Integrations | `GET /integrations?status&provider` · `GET /tenants/{id}/integrations` | `platform:read` |
| Jobs | `GET /jobs?tenant&status&type&from&to` · `GET /jobs/{id}` | `platform:read` |
| | `POST /jobs/{id}/retry` (failed only) · `POST /tenants/{id}/forecasts` | `jobs:write` |
| Signals | `GET /tenants/{id}/signals` | `platform:read` |
| Support | `POST /tenants/{id}/support-sessions` · `GET /tenants/{id}/support-sessions/active` · `POST /support-sessions/{sid}/end` | `support:open` |
| Audit | `GET /audit?actor&action&tenant&outcome&from&to` | `platform:read` |
| | `GET /tenants/{id}/audit` 🔒 | `platform:read` |
| Health | `GET /health` | `platform:read` |

Errors follow the existing exception classes: 401 unauthenticated, 403
unauthorized, 404 missing (including cross-tenant nested ids), 409 state
conflicts (slug taken, industry locked, live subscription exists, last owner,
job not failed, tenant suspended for a trigger), 422 validation, 503 when a
dependency is unconfigured or down (Razorpay, Redis for retry). Admin routes
never return 402: operators are not subject to the customer paywall.

Mutating admin requests accept `Idempotency-Key` (existing middleware); the
console sends one for create tenant, assign plan, import and trigger forecast.

### 8.4 Metric definitions

All from real rows; the operator tenant and the sandbox are excluded from
customer metrics and counted separately as internal/demo.

| Metric | Definition |
|---|---|
| Total tenants | customer tenants |
| Active tenants | entitled subscription (`active`/`trialing`, `current_period_end > now()`) and status not suspended/cancelled |
| Trial tenants | entitled via `trialing` |
| Suspended / archived | `status = 'suspended'` / `'cancelled'` |
| Active subscriptions | `status = 'active'` and `current_period_end > now()` |
| MRR | Σ plan `base_price_cents` over active subscriptions (yearly ÷ 12), INR. Labelled "Razorpay-billed plans"; zero-price contracts are listed, not valued (their value is not stored) |
| Total users / SKUs | active users / active SKUs in customer tenants |
| Forecast jobs today | hybrid runs created since 00:00 UTC |
| Failed / pending jobs | `failed` in the last 24 h / `pending` + `running`; **stale** = pending > 15 min or running > 20 min |
| Integration failures | connections with `status = 'error'` |
| Recent system events | last 20 `platform_audit_events` |
| Recent tenant activity | last 20 `audit_log` rows across customer tenants — action, entity type, tenant, time only (no values) |

Tenant health (list filter and badge): **red** = integration in error, a failed
job in 24 h, or subscription `past_due`; **yellow** = stale job, over a limit,
or no entitled subscription; **green** otherwise. Activity buckets from
`max(users.last_login_at)`: 7 d, 30 d, dormant, never.

Usage (per tenant): active SKUs vs `max_skus` and the plan's `active_sku`
quota; active users vs `max_users` and `user_seat`; pending invites; forecast
runs (30 d); API requests this period (`usage_events.api_request`); imports
(30 d, from audit actions); connected integrations; tenant-specific signal rows
(30 d); sales rows (data volume). ≥ 80 % = approaching, ≥ 100 % = over.
Per-tenant storage bytes are not measured and are not shown.

### 8.5 Health checks

| Component | Green | Yellow | Red |
|---|---|---|---|
| API | responding (version, git SHA, env) | — | — |
| Database | reachable, migrations at head, RLS enforced (role not superuser/BYPASSRLS, FORCE on `tenants`) | latency > 500 ms or migrations behind | unreachable or RLS not enforced |
| Redis | ping OK | not configured (in-process mode) | configured, ping fails |
| ML service | `GET /health` 200 within 2 s | — | error or timeout |
| Worker | arq health-check key fresh, queue depth ≤ 20, no stale jobs | queue > 20 or stale jobs; or Redis absent (in-process fallback, not durable) | no heartbeat with Redis configured |
| Integrations | no connection in error; background leader lease held | a connection in error; or no leader lease with Redis configured | a connection in error > 24 h |
| MFA | enforced | not enforced in production | — (dev: "not applicable") |

Each component returns status, a one-line reason, latency where measured, and
`checked_at`.

## 9. Onboarding workflow

`/admin/onboarding` lists tenants still onboarding with checklist progress.
`/admin/onboarding/new` starts the wizard; `/admin/tenants/{id}/onboarding`
resumes it. Each step persists server-side when submitted; the browser holds no
progress of its own.

| # | Step | Behaviour |
|---|---|---|
| 1 | Customer | Company name, company identifier, slug (live availability), primary contact, contact email, industry, region, timezone, plan, SKU limit, seat limit. Submit → `POST /tenants` (create via `create_tenant`, profile, limits) then `POST /tenants/{id}/subscription`. A plan failure after creation shows "Tenant created, plan not assigned — {reason}" with a retry. |
| 2 | Administrator | Name, email, role (owner by default; admin allowed; more can be added). Returns the one-time link with copy button, labelled **not emailed**. |
| 3 | Industry workspace | Shows the industry, confirms its profile exists, shows lock state; correction allowed while unlocked. |
| 4 | Defaults | Horizon (industry default or override), required signal types (read-only) and custom signal types, focus watchlist, SKU and seat limits, audit level (read-only, from the industry). |
| 5 | Data source | CSV/XLSX import on the customer's behalf (sales, products, inventory; column mapping via analyze). Shopify, WooCommerce and SQL sources show live status and "Customer connects this from Workspace → Integrations" — customer credentials never pass through SANKET staff. |
| 6 | Validate | Dry run first (received / would accept / rejected by reason / in-file duplicates), then "Import N rows" with the real result, then the data-quality summary (score, duplicates, missing fields). |
| 7 | Initial forecast | `POST /tenants/{id}/forecasts` → same arq job, `trigger_source = platform_admin`; live status; error text and retry on failure. |
| 8 | Readiness | Computed checklist; **Mark operational** enabled only when blocking items are done. |

Checklist (computed):

| Item | Done when | Blocking |
|---|---|---|
| Tenant created | tenant exists | yes |
| Administrator invited | an owner/admin invite exists (pending or accepted) or an active owner exists | yes |
| Administrator active | an owner has signed in | no |
| Industry configured | an `industry_profiles` row exists for `tenants.industry` | yes |
| Subscription configured | entitled subscription (states shown: none / pending payment / pending contract / entitled / past due) | yes |
| Data connected | readiness `data_source` done | yes |
| Historical data imported | sales rows > 0 (weeks covered shown; < 12 weeks is a warning) | yes |
| Initial forecast completed | readiness `first_forecast` done | yes |

**Mark operational** sets `settings.onboarding` to `complete` (the same shape
the customer wizard writes), which locks the industry, so the customer lands on
their dashboard rather than the wizard.

Enterprise path: step 1 leaves the subscription `incomplete`; a super admin
activates the contract (end date, reference, reason) from the Subscription tab
or the readiness step.

## 10. Frontend

- **Routes** (one lazy chunk, `pages/admin/AdminApp.tsx`, mounted at
  `/admin/*` in `App.tsx`): `/admin/login`, `/admin`, `/admin/tenants`,
  `/admin/tenants/:id/:tab?`, `/admin/tenants/:id/onboarding`,
  `/admin/onboarding`, `/admin/onboarding/new`, `/admin/users`,
  `/admin/subscriptions`, `/admin/usage`, `/admin/integrations`, `/admin/jobs`,
  `/admin/health`, `/admin/audit`, `/admin/security` (MFA enrollment).
- **Guard.** `AdminRoute`: not signed in → `/admin/login`; signed in and
  `GET /admin/me` is 403 → the standard 404 page (the console is not
  advertised); `mfa_satisfied: false` → `/admin/security`; otherwise render.
  The backend check is the boundary; the guard is presentation.
- **Login.** `/admin/login` uses the existing auth store. Dev mode posts the
  operator slug (`VITE_PLATFORM_TENANT_SLUG`, default `sanket-platform`).
  Firebase mode handles `auth/multi-factor-auth-required` with a TOTP resolver.
  `Login.tsx` is not modified.
- **MFA enrollment.** TOTP via the Firebase SDK; the shared secret is shown for
  manual entry (no QR dependency). Needs a Firebase project with Identity
  Platform + TOTP; verified with mocks here, not live.
- **Shell.** Left nav: Dashboard, Tenants, Onboarding, Users, Subscriptions,
  Usage, Integrations, Forecast Jobs, System Health, Audit Logs. Top bar: global
  search (`/` to focus, debounced), notifications bell (`/admin/notifications`),
  operator name + platform role, sign out. A permanent
  **INTERNAL · PLATFORM CONSOLE** marker and an environment badge.
- **Tenant detail tabs.** Overview · Users · Subscription · Usage · Industry ·
  Data · Integrations · Forecast Jobs · Signals · Audit Log 🔒 · Settings. Gated
  panels offer an "Open support session" form; an active session shows a
  **SUPPORT MODE** banner with tenant name and countdown.
- **States.** Every view has loading skeleton, empty state, error state with
  retry, and toasts quoting the server's message. Every mutation goes through
  `ConfirmDialog`; destructive actions (suspend, archive, disable user, cancel
  subscription, activate contract) require a reason; archive requires the slug.
- **Files.** `pages/admin/*`, `components/admin/*`, `api/admin.ts` (on the
  existing `apiClient`), `hooks/usePlatformAdmin.ts`. Icons via `icons.tsx`
  only. No new dependencies.

## 11. Testing and verification

Strict TDD per AGENTS.md: failing test first, then the code.

**Backend (pytest + testcontainers + real Alembic chain; RLS asserted as
`sanket_app`)**

| Suite | Proves |
|---|---|
| `test_admin_route_guard.py` | Enumerates every `/api/v1/admin/*` route from the app and asserts 401 without a token and 403 for customer owner/admin/analyst/viewer tokens. A future unguarded endpoint fails it. |
| `test_platform_authz.py` | Operator user without a role → 403; deactivated role → 403; support cannot mutate; admin cannot use super-admin actions; MFA enforced when required; the DB trigger rejects a customer user. |
| `test_platform_rls.py` | Platform tables invisible and unwritable from a tenant-scoped session; audit table UPDATE/DELETE are no-ops; support session > 2 h rejected by the DB; any write through `platform_read` is refused by the database. |
| `test_admin_tenants.py` | Create (slug conflict, reserved slug, profile, limits), filters, overview, patch, suspend/reactivate/archive, operator tenant hidden and untouchable, suspended tenant gets 402 on a gated route. |
| `test_admin_users.py` | Owner invite via admin; customer invite still rejects owner; role change; last-owner guard; revoke sessions; cross-tenant user id → 404. |
| `test_admin_billing.py` | Assign (fake Razorpay client), contract activation constraints, cancel, entitlement status, 402 behaviour preserved for unsubscribed tenants. |
| `test_admin_onboarding.py` | Checklist against real rows; validation categories and duplicates; import; forecast trigger enqueues with `trigger_source` (fake arq pool); retry only failed; mark operational requires blockers cleared. |
| `test_admin_audit.py` | Every mutation writes both logs; a forced audit failure rolls back the action; denied attempts recorded. |
| `test_admin_support.py` | Gated views 403 without a session, 200 with; expired, other operator's, and other tenant's sessions all 403. |
| `test_admin_secrets.py` | No admin response contains any §6.3 secret field. |
| `test_cross_tenant_isolation.py` | Tenant A cannot read or modify B; `tenant_id` in URL/body/header grants nothing; mismatched `X-Industry-Code` → 403; customer token on admin API → 403; platform access leaves audit rows. |
| `test_admin_health.py` | Status colours from simulated failures. |

**Frontend (Vitest):** `AdminRoute` redirects; confirm dialogs require reason /
slug; support banner countdown and expiry; wizard step gating; readiness list;
MFA resolver with mocked Firebase.

**E2E (Playwright, `e2e/admin-console.spec.ts`):** platform login → create
Chandler Fashions → Fashion → Chandler owner invite → open tenant → usage →
onboarding action (import + trigger forecast) → customer user blocked from
`/admin` → Chandler blocked from another tenant → action visible in the audit
log. Needs Postgres + Redis, migrations, a backend on `127.0.0.1:8000`, and a
bootstrapped admin. The forecast assertion is "queued and status shown";
"completed" only if the ML service is up — reported as observed.

**Before claiming completion:** `ruff check app`, `ruff format --check app`,
`mypy app`, full `pytest`, `bandit` (as CI does); Alembic upgrade → downgrade →
upgrade on a scratch DB; frontend `typecheck`, `lint`, `test`, `build`, and a
check that the admin chunk is absent from the customer entry bundle;
`docker compose config` and image builds; `kubectl kustomize` for both overlays.
Baseline results of both suites are recorded before any change, so
pre-existing failures are not reported as regressions. Reviews:
`security-review` and `superpowers:requesting-code-review`. (gstack `/cso` is
not installed and will not be claimed.)

## 12. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PLATFORM_OPERATOR_TENANT_SLUG` | `sanket-platform` | Operator tenant slug (reserved) |
| `PLATFORM_ADMIN_REQUIRE_MFA` | unset → on in production | Require a second factor on admin endpoints |
| `PLATFORM_SUPPORT_SESSION_MAX_MINUTES` | `120` (max 120) | Support session length cap |
| `VITE_PLATFORM_TENANT_SLUG` | `sanket-platform` | Frontend, dev-login only |

Documented in `.env.example`, `infra/kubernetes/base` config, and
`docs/ADMIN_CONSOLE.md` (security boundaries, RLS interaction, bootstrap
runbook). `docs/ARCHITECTURE.md` gains a pointer.

## 13. Milestones

Each ends with its tests, lint, types and build green, and a commit.

| | Scope |
|---|---|
| M0 | Baseline test results recorded |
| M1 | Migration 0022, models, `platform_authz`, fail-closed audit, `platform_read`, bootstrap CLI, `/admin/me`, `/admin/session`, route-guard test; frontend `AdminRoute`, `/admin/login` (+ MFA), shell |
| M2 | Dashboard, notifications, search, tenant list + detail read views, platform audit, health, support sessions + gated views |
| M3 | Tenant lifecycle + suspension enforcement, industry correction + profile, users/invites/roles/revocation |
| M4 | Billing (assign, activate contract, cancel), usage |
| M5 | Validate/import, forecast trigger/retry, readiness, wizard, mark operational, Jobs page |
| M6 | Isolation/IDOR suite, Chandler E2E, security + code review, docs, deployment checks, final report |

## 14. Out of scope and known limitations

- Managing platform admins from the UI (CLI only).
- Impersonation of any kind.
- Email delivery (invites return a link).
- Industry change after lock, or any data migration between industries.
- In-place plan change, pause/resume.
- A Razorpay webhook event log.
- SKU-limit enforcement on imports and connectors (shown, not enforced).
- Per-tenant storage size.
- Dev-mode tokens cannot be revoked (≤ 60 min lag); production ≤ 60 s.
- Suspended tenants can reach ungated setup routes until their tokens expire or
  revocation propagates.
- The MFA flow is verified with mocks; live verification needs Firebase
  Identity Platform with TOTP enabled.
- Upgrade path: moving `platform_read` onto a dedicated SELECT-only Postgres
  role with column grants (design Approach B) changes only `data_access.py`.
