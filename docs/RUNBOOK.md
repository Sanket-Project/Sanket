# SANKET Runbook

Common incidents and how to recover. Pages by service.

## Backend (FastAPI, port 8000)

### Symptom: `/health` returns `{"db":"unreachable"}`

1. Check Postgres pod:
   `kubectl -n sanket get pods -l app=postgres -o wide`
2. Verify the secret matches the StatefulSet env:
   `kubectl -n sanket get secret sanket-secrets -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d`
3. Tail backend logs for `database.healthcheck.failed`. The exception type
   pinpoints the cause:
   - `OperationalError` → network / pod not ready
   - `InvalidAuthorizationSpecificationError` → password mismatch
   - `InsufficientPrivilegeError` → `sanket_app` role lacks GRANTs from
     `sql/003_rls_policies.sql`. Re-apply that file.

### Symptom: backend pods CrashLoopBackOff in production with `ValueError: Firebase is not configured ... APP_ENV=production`

The production overlay sets `APP_ENV=production`. `config.require_firebase_in_production`
refuses to boot in production unless Firebase is configured (the local dev-login
fallback must never be active in prod). The fix is to populate the
`sanket-firebase` secret — it ships with `REPLACE_ME` placeholders.

```bash
# 1. Project id (required). With GKE Workload Identity this alone is enough.
kubectl -n sanket create secret generic sanket-firebase \
  --from-literal=FIREBASE_PROJECT_ID=<your-firebase-project> \
  --from-literal=FIREBASE_CREDENTIALS_PATH=/var/run/secrets/firebase/service-account.json \
  --from-file=service-account.json=./firebase-sa.json \
  --dry-run=client -o yaml | kubectl apply -f -
# 2. Roll the backend so it picks up the new secret.
kubectl -n sanket rollout restart deployment/backend
```

Two supported credential modes (see `infra/kubernetes/base/secrets.yaml`):
- **Workload Identity / ADC** — set only `FIREBASE_PROJECT_ID` and drop the
  service-account file; firebase-admin uses application-default credentials.
- **Service-account JSON** — set `FIREBASE_CREDENTIALS_PATH` and mount the JSON
  via the `service-account.json` secret key (already wired as the
  `firebase-credentials` volume on the backend Deployment).

Verify before rolling: `kubectl -n sanket get secret sanket-firebase -o jsonpath='{.data.FIREBASE_PROJECT_ID}' | base64 -d`
must not print `REPLACE_ME`.

Staging/dev deliberately keep the dev-login fallback: the staging overlay blanks
`FIREBASE_PROJECT_ID`/`FIREBASE_CREDENTIALS_PATH` (`Settings.firebase_enabled == False`),
and `APP_ENV=staging` does not trigger the production guard.

### Symptom: 401s on every request after a deploy

The JWT secret rotated. Issue an org-wide forced re-login by bumping the
secret in `sanket-secrets` *and* clearing all rows from `refresh_tokens`:

```sql
TRUNCATE refresh_tokens;
```

### Symptom: `429 Rate limit exceeded` cluster-wide

In-process token-bucket — the buckets reset when a pod restarts. If sustained,
either raise `RATE_LIMIT_PER_MINUTE` env on the deployment OR switch to the
Redis-backed implementation (see `app/middleware/rate_limit.py` header).

## ML API (FastAPI, port 8001)

### Symptom: `/health` shows `"chronos_preloaded": false`

The lifespan preload failed. Most common causes:

| Cause | Diagnosis | Fix |
|------|-----------|-----|
| HF download blocked by NetworkPolicy | `kubectl logs <pod> \| grep huggingface` | Add egress allow for huggingface.co |
| OOM during model decode | `kubectl describe pod` shows OOMKilled | Raise memory request to 8Gi for T5-Large |
| Wrong `chronos-forecasting` version | ImportError in logs | Pin to >=1.4 |

The first `POST /forecast` will retry the load — if it succeeds the gauge
flips to `true`. Otherwise the request returns 503.

### Symptom: forecast request hangs > 60s

If trained-path: ensemble.joblib may have a stale torch reference. Check
artifact directory mtime; the simplest fix is to delete the artifact dir
and let it re-train or fall back to zero-shot.

If zero-shot: usually means context history is unusually long. The default
caps at 104 weeks per series and 500 series — increase the K8s memory
request before raising those bounds.

## Database

### Symptom: `permission denied for table products` from the application

The `sanket_app` role is missing a grant. Re-apply RLS file:
```bash
psql -U postgres -d sanket -f backend/sql/003_rls_policies.sql
```

### Symptom: query returns zero rows even though data exists

You forgot `SET LOCAL app.current_tenant_id`. The RLS policy hides everything
when the GUC is empty. Always go through `Database.session(tenant_id=…)`,
never `engine.connect()` directly from request paths.

### Symptom: `historical_sales` partition write fails

The default partition range covers 2022–2027. After Jan 2028, create new
quarterly partitions. The DO block in `002_schema.sql` shows the template.

## Pharma / GxP

### Symptom: A QA release endpoint returns 422 `cold chain missing temperature`

The batch row has `cold_chain_required=TRUE` but `storage_temp_min_c/max_c`
are NULL. This is intentional — the SQL `chk_cold_chain_temps` CHECK
constraint enforces it. Operator must record temperatures before release.

### Symptom: an auditor reports missing audit rows

The `audit_log` table is protected by `RULE no_update_audit / no_delete_audit`,
so the only ways rows can be missing are:
1. The application failed to call `audit.record()` — grep for `audit.write.failed`
   in structured logs (the helper swallows errors so as not to block business
   logic; failures are logged with full context).
2. The DB was restored from a backup taken before the action. Cross-check with
   the application's structured log stream which mirrors every audited event.

## Deploys

### Rollback

```bash
# Last good image tag
kubectl -n sanket set image deployment/backend api=ghcr.io/sanket/backend:sha-<good>
kubectl -n sanket rollout status deployment/backend
```

Or via Kustomize: edit `infra/kubernetes/overlays/<env>/kustomization.yaml`
`images.newTag` and re-apply.

### Stuck rollout

```bash
kubectl -n sanket rollout undo deployment/backend
kubectl -n sanket describe pod -l app=backend | tail -50
```

## Phase 1 hardening — HA, pooling, admission control, idempotency

Database HA, PgBouncer, backups, and PITR have a dedicated runbook:
[`docs/DISASTER_RECOVERY.md`](DISASTER_RECOVERY.md).

### Symptom: ML forecasts return `429 inference overloaded`

Admission control in the ML API is shedding load (see
`sanket_ml/inference/throttle.py`). The `detail` says which limit hit:
- `tenant_rate_limited` — one tenant exceeded `ML_INFERENCE_TENANT_RATE_PER_MIN`.
- `overloaded` / `queue_timeout` — the replica is at capacity.

```bash
curl -s http://ml-api:8001/health | jq .throttle      # inflight / capacity / counters
curl -s http://ml-api:8001/metrics | grep rejected     # per-reason counters
```
Fix: scale `ml-api` replicas, or raise `ML_INFERENCE_MAX_CONCURRENT` if CPU has
headroom. Alert: `SanketInferenceLoadShedding`.

### Symptom: background pollers / webhook retries appear to run multiple times

They shouldn't — singleton loops are gated by a Redis leader lease
(`app/core/distributed_lock.py`). If you see duplicates:
```bash
# Who holds the lease?
redis-cli get sanket:leader:background-singletons
# Logs on each replica:
kubectl -n sanket logs -l app=backend | grep -E "leader.(acquired|lost|singletons)"
```
If `REDIS_URL` is unset, every replica runs the loops in-process (expected in
single-node dev). Ensure `REDIS_URL` is set in multi-replica environments.

### Symptom: a client double-submitted and got two side effects

Have clients send an `Idempotency-Key` header on mutating requests. With Redis
configured, retries replay the first response (`Idempotency-Replayed: true`
header) and never re-execute. Without Redis the middleware is a pass-through —
confirm `REDIS_URL` is set.

### Symptom: provider webhook processed twice

Replay protection (`app/core/webhook_replay.py`) de-dupes on the provider
delivery id (`X-Shopify-Webhook-Id` / Razorpay event id) and rejects stale
events. A duplicate is logged (`*.webhook.replay_dropped`) and acked 200 so the
provider stops retrying. If Redis is down it fails *open* (processes the event)
to avoid dropping legitimate traffic.

### Preflight: secrets audit

Before any deploy:
```bash
APP_ENV=production python -m app.scripts.audit_secrets   # exits non-zero on criticals
```
The app also fails closed at startup in production on weak/default secrets.
