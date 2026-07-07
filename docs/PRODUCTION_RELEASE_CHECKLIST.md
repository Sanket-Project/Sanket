# Production Release Checklist

This branch (`prod-hardening/rls-ml-auth-and-migration-chain`) hardens tenant
isolation, ML-service auth, the migration chain, secrets handling, and adds a
**fail-closed startup guard**. Because of that guard, the release **will not boot
in production until the database role is fixed**. Work top to bottom — do not
skip 1 and 2.

> The application now refuses to start in production when the DB role is a
> SUPERUSER / has BYPASSRLS (see `Database.assert_tenant_isolation_enforced`).
> This is intentional: connecting as such a role silently bypasses every RLS
> policy and exposes tenants to each other. The fix is operational, below.

---

## 0. Pre-flight: rotate the exposed credentials (BLOCKING)

These values were exposed during development and must be rotated before launch.
They are **not** in git history, but treat them as compromised.

| Secret | Rotate at |
| --- | --- |
| Supabase DB password | Supabase Dashboard → Project Settings → Database → Reset database password |
| Firebase service-account private key | GCP Console → IAM → Service Accounts → `firebase-adminsdk-*@<project>` → Keys → delete the old key, add a new JSON key |
| `JWT_SECRET` | `openssl rand -hex 32` (invalidates existing dev tokens only) |
| `ML_SERVICE_TOKEN` | `openssl rand -hex 32` (set identically for backend **and** ml-api) |
| Razorpay keys | Razorpay Dashboard → Settings → API Keys → regenerate |

## 1. Create the non-privileged application DB role (BLOCKING)

The app must connect as a `NOSUPERUSER NOBYPASSRLS` role, never the Supabase
`postgres` superuser. The migrations create `sanket_app`, but on a managed
provider set its password explicitly and confirm its attributes:

```sql
-- As the Supabase postgres admin, once:
ALTER ROLE sanket_app WITH LOGIN PASSWORD '<strong-rotated-password>'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

-- Verify (MUST return: f | f)
SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'sanket_app';
```

Then point the runtime secret at it (NOT `postgres`):

```
DATABASE_URL=postgresql+asyncpg://sanket_app:<password>@<host>:5432/postgres
```

Migrations may still run as the admin/owner role (`DATABASE_URL` for the
migrate-job), but the **backend/worker/ml runtime** must use `sanket_app`.

## 2. Provision Kubernetes secrets (BLOCKING)

Replace every `REPLACE_ME` in `infra/kubernetes/base/secrets.yaml` (via
sealed-secrets / Vault / External Secrets — do not commit real values):

- `sanket-secrets`: `JWT_SECRET`, `ML_SERVICE_TOKEN`, `POSTGRES_PASSWORD`
  (superuser, for the backup job), `METRICS_TOKEN`.
- `sanket-db-url`: `DATABASE_URL` (sanket_app), `ML_DATABASE_URL` (sanket_app).
- `sanket-firebase`: `FIREBASE_PROJECT_ID` and either Workload Identity (ADC) or
  the rotated service-account JSON. Prefer `FIREBASE_CREDENTIALS_JSON`
  (base64) over a file path in containers.
- `backup-aws`: S3 credentials for the nightly `pg_dump` CronJob.

Confirm `ML_SERVICE_TOKEN` is **identical** in the backend and ml-api
deployments, or the (now fail-closed) ML service returns 503.

## 3. Wire metrics scraping

`/metrics` now requires `METRICS_TOKEN` and fails closed in production. Configure
the in-cluster Prometheus scrape to send `Authorization: Bearer <METRICS_TOKEN>`
(or `X-Metrics-Token`), otherwise production metrics go dark.

## 4. CI green on the PR

Open the PR for this branch and confirm:
- `backend-ci`: lint + types + **`test_rls_isolation.py`** + `pip-audit`
- `frontend-ci`, `ml-ci`
- `security`: gitleaks + bandit
- `build-images`: Trivy gate (fails on fixable CRITICAL)

## 5. Merge → staging → verify

Merging to `main` auto-deploys to **staging** (`deploy.yml`). On staging:

```sql
-- isolation actually enforced (run as sanket_app):
SET ROLE sanket_app;
SET app.current_tenant_id = '<tenant-A-uuid>';
SELECT count(*) FROM products;            -- only tenant A's rows
-- all tenant tables forced:
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity AND NOT c.relforcerowsecurity;
-- MUST be 0
```

Smoke-test: login, a forecast (through the backend `/forecasts/generate` proxy,
not the ML service directly), a Razorpay webhook, and a couple of authz-denied
calls (a `viewer` hitting `DELETE /products/{id}` → 403).

## 6. Promote to production (manual, human-gated)

GitHub → Actions → **deploy** → *Run workflow* → environment = `production`.
Requires the environment approval. The migrate-job runs `alembic upgrade head`
before rollout. Watch the backend pods reach `Ready`: if the DB role is still
privileged, they will (correctly) refuse to start — go back to step 1.

## 7. Post-deploy verification

- `GET /health` → `{"status":"ok"}` (200, unauthenticated).
- Backend logs show `database.rls_check.ok` (not `rls_check.unenforced`).
- A cross-tenant probe returns no foreign rows.
- Backups: confirm the nightly CronJob produced an object in the S3 bucket.
