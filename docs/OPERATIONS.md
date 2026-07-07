# SANKET Operations Playbook

## Deploying a release

1. Merge PR → `main` triggers `backend-ci`, `ml-ci`, `frontend-ci`.
2. On green, `build-images` builds and pushes `ghcr.io/sanket/{backend,ml-api,frontend}`
   tagged with branch, SHA, and `latest`.
3. `deploy.yml` auto-deploys to **staging** (`sanket-staging` namespace).
4. Verify staging:
   ```bash
   curl https://staging.sanket.example/api/v1/../../health
   curl https://staging.sanket.example/ml/health
   ```
5. Promote to **production** manually:
   ```
   GitHub Actions → deploy → Run workflow → environment: production
   ```

## Running migrations

```bash
# Inside the backend pod
kubectl -n sanket exec -it deploy/backend -- alembic upgrade head

# Or locally against a remote DB
cd backend
DATABASE_URL=postgresql+asyncpg://... alembic upgrade head
```

Always run migrations *before* deploying app code that depends on the new schema.
Use the expand-then-contract pattern:

1. Add nullable column.
2. Deploy code that writes to it.
3. Backfill in batch.
4. Deploy code that requires it non-null.
5. Migration that adds the NOT NULL constraint.

## Onboarding a new tenant

```sql
INSERT INTO tenants (slug, display_name, tier, status, industries, active_industry)
VALUES ('acme-co', 'Acme Co', 'scale', 'active',
        ARRAY['fashion']::industry_code[], 'fashion');

-- Owner user
INSERT INTO users (tenant_id, email, password_hash, full_name, role, active_industry)
VALUES (
  (SELECT id FROM tenants WHERE slug='acme-co'),
  'founder@acme.co',
  '<argon2id hash from passlib>',
  'Jane Founder',
  'owner',
  'fashion'
);
```

Then they can sign in immediately — zero-shot Chronos will serve their first
forecasts until a tenant-trained artifact lands.

## Training a tenant's models

Manually:
```bash
kubectl -n sanket exec deploy/ml-api -- \
  python -m scripts.train_all <tenant_uuid>
```

Scheduled (CronJob):
```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: nightly-train, namespace: sanket }
spec:
  schedule: "0 3 * * *"   # 03:00 UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: train
              image: ghcr.io/sanket/ml-api:stable
              command: [python, -m, scripts.train_all]
          restartPolicy: OnFailure
```

## Scaling

| Service | Bottleneck | Knob |
|---------|------------|------|
| backend | CPU (auth, JSON) | HPA on CPU (set to 70%) |
| ml-api | CPU (Chronos inference) | HPA on CPU (75%); add GPU node pool for production scale |
| postgres | Connections / IO | Scale up vertically; add read replica + route reads via SQLAlchemy `Engine` URLs |
| frontend | Bandwidth | CDN in front of the Ingress |

## Backup & restore

PostgreSQL — daily PITR via WAL shipping (cluster operator's responsibility).
Quick logical backup:
```bash
kubectl -n sanket exec -it postgres-0 -- \
  pg_dump -U sanket_app -Fc sanket > sanket-$(date +%F).dump
```

Restore:
```bash
kubectl -n sanket exec -i postgres-0 -- \
  pg_restore -U sanket_app -d sanket --clean --if-exists < sanket-2026-05-25.dump
```

ML artifacts — the `ml-artifacts` PVC. Snapshot via your CSI's
VolumeSnapshot resource. They're regenerable from data, so a 7-day
retention is enough.

## Secrets rotation

```bash
# Generate new JWT secret
NEW=$(openssl rand -hex 32)
kubectl -n sanket patch secret sanket-secrets \
  -p "{\"data\":{\"JWT_SECRET\":\"$(echo -n $NEW | base64)\"}}"
kubectl -n sanket rollout restart deployment/backend
# Existing access tokens become invalid; clients use refresh tokens to re-establish.
```

For DB password rotation, use the `ALTER ROLE ... PASSWORD` then secret-patch
sequence — see `RUNBOOK.md` for the no-downtime variant.

## Cost controls

- `ml-api` is the heaviest line item. The default Chronos model is
  `amazon/chronos-t5-large`; set `ML_CHRONOS_REPO=amazon/chronos-t5-small`
  in resource-constrained environments — accuracy drops modestly but
  memory falls from ~3 GiB to ~300 MiB.
- Foundation-model weight cache is shared via the `hf-cache` emptyDir;
  promote to a PVC to avoid re-downloads on every pod restart.
- Set `ML_CHRONOS_PRELOAD_ON_STARTUP=false` if cold latency on first
  request is acceptable; saves ~3 GiB resident per pod.
