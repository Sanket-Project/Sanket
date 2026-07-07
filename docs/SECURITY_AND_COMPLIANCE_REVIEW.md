# SANKET — Enterprise Security & Compliance Review

**Author:** Enterprise Security Architect
**Date:** 2026-06-15
**Type:** Current-state security review, gap analysis, phased roadmap, and compliance
readiness assessment — grounded in the actual codebase (file references throughout).

> **Scope & honesty note.** This is an **assessment and design** deliverable, not a
> set of half-built auth features. Identity and tenant-isolation code is the highest-
> blast-radius area in the system; the responsible sequence is *assess → design →
> implement incrementally with review*, which is what this document sets up. Where I
> say a control "exists" I have read the code that implements it; where I say
> "partial" or "absent" I have verified the gap. **No claim here asserts that SANKET
> is certified** for SOC 2 / ISO 27001 / GDPR / 21 CFR Part 11 — certification is an
> organizational + evidentiary process. This rates **technical readiness** and the
> gaps to close.

---

## 1. Executive summary

SANKET's **tenant isolation is genuinely strong** and ahead of most early-stage
multi-tenant SaaS: Postgres `FORCE ROW LEVEL SECURITY`, a dedicated
`NOSUPERUSER NOBYPASSRLS` runtime role, and a **fail-closed startup assertion** that
refuses to boot in production if the DB role could bypass RLS
([`core/database.py`](../backend/app/core/database.py) `assert_tenant_isolation_enforced`).
Authentication is delegated to Firebase (a sound choice — no hand-rolled crypto), with
tenant/role context carried in verified custom claims.

The gaps are concentrated in **enterprise identity lifecycle** (SSO/SAML federation,
SCIM, MFA are not yet wired) and **authorization breadth** (a good RBAC primitive
exists but is enforced on only ~4 of ~21 routers). Audit logging is append-only at the
DB layer but **not tamper-evident**, and secret encryption lacks **KMS-backed key
management and rotation**.

**Overall posture:** solid foundation, **not yet enterprise-ready**. No critical
*open-door* vulnerabilities were found in the reviewed paths; the risks are
*completeness* and *lifecycle* gaps that enterprise buyers and auditors will require.

**Top 5 priorities (detail in §4):**
1. **RBAC coverage sweep** — most mutating endpoints lack an explicit role check (High).
2. **MFA enforcement** via Firebase/GCIP, incl. step-up for sensitive/e-sign actions (High).
3. **Tamper-evident + WORM audit storage** — hash-chain + S3 Object Lock export (High; Part 11 blocker).
4. **KMS-backed encryption keys with rotation** — replace the static derived Fernet key (High).
5. **SSO/SAML (GCIP) + SCIM** for enterprise provisioning/deprovisioning (High; sales blocker).

---

## 2. Current-state security review

Severity scale: **Critical** (exploitable now) · **High** (enterprise/compliance
blocker) · **Medium** (hardening) · **Low** (hygiene).

### 2.1 Identity

| Capability | Status | Evidence / gap |
|---|---|---|
| Federated SSO (OIDC/SAML) | **Partial — broker ready, not configured** | The backend already consumes verified Firebase ID tokens with tenant claims ([`firebase_auth.py`](../backend/app/core/firebase_auth.py), [`tenant_context.py`](../backend/app/middleware/tenant_context.py)). Firebase → **Google Cloud Identity Platform (GCIP)** supports per-tenant SAML/OIDC IdPs. What's missing: per-tenant IdP configuration, home-realm discovery, and JIT provisioning/claim mapping. |
| SAML | **Absent (by delegation)** | Correctly **not** terminated in-app (don't roll your own SAML). Path = GCIP SAML providers. Greenfield: tenant↔IdP mapping + assertion→claim mapping. |
| SCIM 2.0 | **Absent** | No user-lifecycle endpoints exist. `signup` creates a tenant owner ([`auth.py`](../backend/app/routers/auth.py)); there is no invite, no `/Users`/`/Groups`, no automated deprovision. Deactivation is a manual `is_active` flag. Enterprise auto-deprovision (offboarding) is unmet. |
| MFA | **Absent (schema stub only)** | `users.mfa_secret` / `users.mfa_enabled` columns exist ([`sql/002_schema.sql`](../backend/sql/002_schema.sql)) but are **never read or enforced** anywhere in the codebase. No TOTP/WebAuthn flow, no step-up. |
| Brute-force protection | **In place** | Per-account **and** per-IP lockout with Redis ([`core/login_attempt.py`](../backend/app/core/login_attempt.py)), applied on the dev-login path. |
| Token hygiene | **In place** | Short-lived dev tokens fenced from production; revocation check cached per-UID with TTL; logout revokes Firebase refresh tokens ([`auth.py`](../backend/app/routers/auth.py) `logout`). |

### 2.2 Security (authz, audit, encryption)

| Capability | Status | Evidence / gap |
|---|---|---|
| RBAC primitive | **Good, but sparsely applied — High** | [`core/rbac.py`](../backend/app/core/rbac.py) provides a clean, centralized `require_role(...)` with `require_admin`/`require_owner`. **But** it is wired into only ~4 routers (`inventory`, `products`, `webhooks`, `auth`). The other ~17 routers rely on tenant scoping alone, so a `viewer` may reach mutating endpoints that should be admin-only. **Authorization is not deny-by-default at the role layer.** |
| Granular permissions | **Absent — Medium** | Only 5 coarse roles (`owner/admin/analyst/viewer/api_service`). No resource:action permission model, no per-feature scopes, no custom roles — enterprises will ask for both. |
| Audit logging | **Partial — Medium/High** | [`services/audit.py`](../backend/app/services/audit.py) writes to `audit_log` with who/what/when/old/new. **Coverage is incomplete** (auth events are logged; many data mutations are not verified to log). Writes are **fail-open** (errors swallowed) — acceptable for availability but a Part 11/SOC 2 concern for security-relevant events, which should fail-closed. |
| Immutable audit storage | **Partial — High** | Logical append-only is enforced: `RULE no_update_audit` / `no_delete_audit` ([`sql/002_schema.sql`](../backend/sql/002_schema.sql)) plus grants that give `sanket_app` only `SELECT, INSERT` ([`sql/003_rls_policies.sql`](../backend/sql/003_rls_policies.sql)). **However:** (a) a superuser (used by migrations/backups) can still `TRUNCATE`/alter, (b) there is **no cryptographic tamper-evidence** (no hash chain), and (c) there is **no WORM** archival. This is **not** "immutable" to an auditor. |
| Encryption in transit | **Assumed in place** | TLS terminated at ingress (k8s). Internal service-to-service TLS not verified in manifests — confirm. |
| Encryption at rest (secrets) | **Partial — High** | [`core/crypto.py`](../backend/app/core/crypto.py) encrypts integration tokens with Fernet (AES-128-CBC + HMAC). Gaps: the key is `SHA-256(secret)` with **no KDF salt/stretching**, **no rotation** (changing the secret breaks all ciphertexts), a single process-cached key, and **no KMS/envelope encryption**. Scope is integration tokens only — **PII is not field-encrypted**. |
| Database encryption at rest | **Provider-managed** | Relies on cloud/CNPG volume encryption — confirm enabled and document. |
| Secret management | **Good** | Fail-closed weak-secret checks in production ([`config.py`](../backend/app/config.py) `reject_weak_secrets_in_production`); a secrets audit script exists ([`scripts/audit_secrets.py`](../backend/app/scripts/audit_secrets.py)); k8s secrets templated. |

### 2.3 Multi-tenancy

| Capability | Status | Evidence / gap |
|---|---|---|
| Row-level security | **Strong** | RLS enabled + policy on every tenant table; `USING (bypass_rls() OR tenant_id = current_tenant_id())` ([`sql/003_rls_policies.sql`](../backend/sql/003_rls_policies.sql)). Omitted `WITH CHECK` means the `USING` clause is also applied on INSERT, so **cross-tenant inserts are blocked**. `current_tenant_id()` returns NULL when unset → zero rows (**fail-closed default**). |
| Forced RLS + role hardening | **Strong** | `FORCE ROW LEVEL SECURITY` (migration 0011) defeats table-owner bypass; runtime role is `NOSUPERUSER NOBYPASSRLS`; startup **refuses to boot** in prod if this is violated ([`core/database.py`](../backend/app/core/database.py)). This is the single best control in the system. |
| Request→DB tenant binding | **In place** | Per-request transaction sets `app.current_tenant_id` via `SET LOCAL`/`set_config(..., true)` ([`core/database.py`](../backend/app/core/database.py) `session()`), which is transaction-pooler-safe (no GUC leakage). Workers use an explicit `bypass_rls` session. |
| Bypass surface | **Acceptable, Low** | `bypass_rls` is a GUC only set in `session_no_rls()`. Recommend a lint/test ensuring no router uses `session_no_rls` for tenant-scoped reads. |
| Encryption strategy (tenant data) | **Partial — see 2.2** | No per-tenant key separation; a single platform key. Enterprises in regulated verticals may require per-tenant (BYOK) keys. |

---

## 3. Gap register

| ID | Area | Sev | Finding | Recommendation |
|----|------|-----|---------|----------------|
| ID-1 | Identity | High | No SCIM; no automated deprovision | Build SCIM 2.0 (Users/Groups); deactivate + revoke on deprovision |
| ID-2 | Identity | High | MFA unenforced (schema stub only) | Enforce via GCIP; step-up for sensitive/e-sign ops |
| ID-3 | Identity | High | SSO/SAML not configured per tenant | GCIP per-tenant providers + JIT provisioning + claim mapping |
| SEC-1 | Authz | High | RBAC on ~4/21 routers | Coverage sweep; deny-by-default; tests asserting role on every mutation |
| SEC-2 | Authz | Medium | No granular permissions/custom roles | Introduce permission model (role→permission, resource:action) |
| SEC-3 | Audit | High | Not tamper-evident; not WORM | Hash-chain rows + S3 Object Lock export; restrict superuser truncation |
| SEC-4 | Audit | Medium | Incomplete coverage; fail-open | Audit all mutations; fail-closed for security-critical events |
| SEC-5 | Crypto | High | Static derived key, no KMS, no rotation | KMS envelope encryption + key IDs + rotation |
| SEC-6 | Crypto | Medium | PII not field-encrypted | Field-level encryption for sensitive PII; per-tenant key option |
| MT-1 | Tenancy | Low | `session_no_rls` misuse risk | Add a test/lint preventing tenant reads via the bypass session |
| MT-2 | Tenancy | Medium | No per-tenant key separation | Offer BYOK / per-tenant DEK for regulated tenants |

No **Critical** (actively exploitable) findings in the reviewed code paths.

---

## 4. Phased roadmap & migration plans

Sequenced low-risk-first; each item is independently shippable and reversible.

### Phase 0 — Authorization & audit hardening (weeks 0–4)
*Highest ROI, lowest risk, no external dependencies.*

- **SEC-1 RBAC coverage sweep.** Apply `require_role([...])` to every mutating
  endpoint; default analysts/viewers to read-only. *Migration:* none (code +
  dependency wiring). *Tests:* parametrized test asserting each `POST/PUT/PATCH/DELETE`
  rejects an under-privileged role. *Backout:* per-router revert.
- **SEC-4 audit completeness + fail-closed.** Route all mutations through an audit
  helper; make security-critical events (role change, member removal, e-sign) fail the
  request if the audit write fails. *Migration:* none.
- **SEC-5 KMS keys (design + cutover).** Introduce envelope encryption: data keys
  wrapped by a KMS CMK; store `key_id` alongside ciphertext. *Migration:* add `key_id`
  column to integration-secret storage; dual-read (old derived key + KMS) during
  cutover; re-encrypt in a background job; drop the legacy path. *Backout:* dual-read
  keeps old ciphertexts valid throughout.

### Phase 1 — Enterprise identity (weeks 4–10)

- **ID-3 SSO/SAML via GCIP.** Configure GCIP multi-tenancy; per-tenant SAML/OIDC
  providers; home-realm discovery by email domain; JIT provisioning that maps IdP
  assertions → SANKET user + custom claims (reuse the existing claim-sync in
  [`auth.py`](../backend/app/routers/auth.py) `session`). *Migration:* add
  `tenant_idp_config` table (tenant_id, provider_id, domain, default_role). *Backout:*
  feature-flag per tenant; password/dev paths unaffected.
- **ID-2 MFA enforcement.** Enable GCIP MFA (TOTP/SMS); enforce via a claim/step-up
  check in `TenantContextMiddleware` for sensitive routes. Remove the unused
  `mfa_secret`/`mfa_enabled` columns **or** wire a self-managed TOTP fallback for the
  dev path. *Migration:* drop or repurpose the stub columns.
- **SEC-2 granular permissions.** Add a `role → permissions` map and `require_permission`
  dependency layered over `require_role` (back-compatible). *Migration:* optional
  `roles`/`permissions` tables if custom roles are needed.

### Phase 2 — Provisioning & immutable audit (weeks 10–18)

- **ID-1 SCIM 2.0.** Implement `/scim/v2/Users` + `/Groups` (RFC 7644); bearer-auth per
  tenant; create/patch/deactivate mapped to SANKET users; on deactivate, set
  `is_active=false` **and** revoke Firebase refresh tokens. *Migration:* `scim_token`
  per tenant; `external_id` on users.
- **SEC-3 tamper-evident + WORM audit.** Add `prev_hash`/`row_hash` (hash-chain) to
  `audit_log`; a daily job anchors the latest hash (and exports the day's segment to
  **S3 Object Lock / compliance mode**). Restrict who can connect as superuser; route
  backups so they cannot silently truncate audit. *Migration:* add hash columns +
  trigger computing `row_hash = H(prev_hash || row)`; new export CronJob (mirrors
  [`infra/cron/`](../infra/cron/)). *Backout:* columns are additive; export is
  out-of-band.

### Phase 3 — Compliance program enablement (continuous)

- **GDPR DSAR.** Build export (extend [`routers/export.py`](../backend/app/routers/export.py))
  and erasure (pseudonymize PII; retain audit with PII minimized); enforce
  `data_retention_days` via a scheduled purge. PII inventory + sub-processor register.
- **Part 11 e-signatures.** Capture signature manifestation (printed name, UTC
  timestamp, **meaning** of signing) and cryptographically link signature↔record;
  require MFA at signing. Author IQ/OQ/PQ validation docs.
- **SOC 2 / ISO 27001 evidence.** Policies, access reviews, vendor management, change-
  management evidence (already strong via Alembic + git + CI).

---

## 5. Compliance readiness

Legend: ✅ control present · ◻ partial · ❌ absent. (Technical readiness only.)

### 5.1 GDPR

| Article | Requirement | Status | Gap / action |
|---|---|---|---|
| Art 5/25 | Data minimization, privacy by design | ◻ | RLS + retention field; no PII inventory/DPIA |
| Art 15/20 | Access & portability | ◻ | `export` router exists; formalize DSAR export |
| Art 17 | Right to erasure | ❌ | Build erasure + pseudonymize audit PII |
| Art 30 | Records of processing | ❌ | Author RoPA + sub-processor register (Firebase, Razorpay, Shopify, cloud) |
| Art 32 | Security of processing | ◻ | RLS/audit strong; encryption KMS gap |
| Art 33/34 | Breach notification | ◻ | Logging present; document the process + runbook |

### 5.2 SOC 2 (Trust Services Criteria)

| Criterion | Status | Notes |
|---|---|---|
| CC6 Logical access | ◻ | RLS strong; **RBAC sparse, MFA absent** (close SEC-1, ID-2) |
| CC7 Ops / monitoring | ◻ | Prometheus alerts + structured logs; need formal alerting + IR runbook |
| CC8 Change management | ✅ | Alembic migrations, git, CI, code review |
| A1 Availability | ✅ | DR doc, backups, PDB, partition automation |
| Confidentiality | ◻ | Encryption present; KMS/rotation gap |

### 5.3 ISO 27001 (Annex A, 2022)

| Control area | Status | Notes |
|---|---|---|
| A.5 Org policies / ISMS | ❌ | Organizational — author ISMS, risk assessment, SoA |
| A.5.15–18 Access control | ◻ | RLS strong; RBAC/MFA partial |
| A.8.15 Logging | ◻ | Append-only; add tamper-evidence + monitoring |
| A.8.24 Cryptography | ◻ | No key-management lifecycle (KMS/rotation) |
| A.8.25–29 Secure development | ✅ | Migrations, tests, secrets checks, security review tooling |
| A.5.29/30 Continuity | ✅ | DR + backup + restore procedures documented |

### 5.4 FDA 21 CFR Part 11 (gap analysis)

| Clause | Requirement | Status | Gap |
|---|---|---|---|
| 11.10(a) | System validation (IQ/OQ/PQ) | ❌ | Author validation package |
| 11.10(d) | Limit access to authorized individuals | ◻ | RLS yes; RBAC sparse; **MFA absent** |
| 11.10(e) | Secure, computer-generated audit trail (who/what/when, old/new) | ◻ | Fields present; **not tamper-evident**, coverage incomplete |
| 11.10(g) | Authority checks | ◻ | Tie to RBAC sweep (SEC-1) |
| 11.50 | Signature manifestations (name, datetime, meaning) | ◻ | `pharma_batches.qa_released_by/at` only — no *meaning*/manifestation |
| 11.70 | Signature/record linking | ❌ | Cryptographically bind signature ↔ record |
| 11.200 | Identification + MFA for e-signatures | ◻ | Unique IDs yes; **MFA required at signing** (ID-2) |

**Part 11 critical path:** ID-2 (MFA) + SEC-3 (tamper-evident audit) + 11.50/11.70
(e-signature manifestation & linking) are the blocking items for the pharma vertical.

---

## 6. What I recommend implementing first

If you want code (not just plan) next, the safest high-value starting points — each a
small, reviewable PR — are, in order:

1. **SEC-1 RBAC coverage sweep** + a deny-by-default test harness (no DB migration,
   immediately auditable, closes the widest gap).
2. **SEC-3 audit hash-chain** migration (additive columns + trigger) — turns "append-
   only" into "tamper-evident", the Part 11/SOC 2 blocker.
3. **SEC-5 KMS envelope encryption** with dual-read cutover.

I did **not** implement any of these in this pass because changing authorization,
audit, and key management without a reviewed plan is exactly how regressions and
lockouts get shipped. Tell me which to start with and I'll do it as its own verified
change with tests.

---

## 7. Sources reviewed

`core/firebase_auth.py`, `core/database.py`, `core/rbac.py`, `core/crypto.py`,
`core/login_attempt.py`, `middleware/tenant_context.py`, `middleware/rate_limit.py`,
`routers/auth.py`, `routers/inventory.py`, `services/audit.py`, `config.py`,
`sql/002_schema.sql`, `sql/003_rls_policies.sql`, migration `0011` (FORCE RLS),
`infra/kubernetes/base/secrets.yaml`. Architecture diagrams accompany this review in
the chat.
