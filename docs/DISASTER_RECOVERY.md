# SANKET — Disaster Recovery & Database HA Runbook

Covers the Phase 1 hardening of the data tier: PostgreSQL high availability,
PgBouncer pooling, continuous backup, automated backup validation, and
point-in-time recovery (PITR).

> **Targets:** RPO ≤ 5 min (continuous WAL archiving) · RTO ≤ 30 min (PITR
> restore drill measures the real number weekly).

---

## 1. Architecture

PostgreSQL is managed by the **CloudNativePG (CNPG)** operator
([`infra/kubernetes/base/postgres.yaml`](../infra/kubernetes/base/postgres.yaml)):

```
                 ┌───────────── PgBouncer poolers (HA) ─────────────┐
   app / worker ─┤ postgres-pooler-rw (→ primary, transaction mode) │
   read paths  ──┤ postgres-pooler-ro (→ replicas)                  │
                 └──────────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────┐
        │  CNPG Cluster "postgres" (3 instances, anti-affinity)     │
        │   primary  ⇄  replica-1 (sync)  ⇄  replica-2 (async)      │
        └───────────────┬───────────────────────────┬──────────────┘
                        │ WAL stream + base backups  │
                        ▼                             ▼
              s3://sanket-backups/postgres-ha   (barman object store)
                 ├── base/   (nightly ScheduledBackup)
                 └── wals/   (continuous archiving → PITR)
```

Key properties that removed the previous single-pod SPOF:

- **3 instances** on `required` pod anti-affinity (never co-located). Automatic
  failover promotes a standby in seconds if the primary dies.
- **Synchronous replication** to ≥1 replica (`minSyncReplicas: 1`) → a committed
  write survives loss of the primary (zero data loss on failover).
- **Continuous WAL archiving** to object storage → PITR to any point in time.
- App traffic flows through **PgBouncer** (transaction pooling) so 5+ API
  replicas + workers multiplex onto a bounded server-connection pool. The app
  runs with `DB_PGBOUNCER_MODE=true` (disables asyncpg prepared statements,
  required under transaction pooling). The tenant-isolation GUC uses `SET LOCAL`
  inside a transaction, so it is pooling-safe (no cross-connection leakage).
- **Migrations bypass the pooler** (`DATABASE_URL_DIRECT` → `postgres-rw`): DDL
  must not run through a transaction pooler.

---

## 2. Prerequisites (one-time)

1. Install the CNPG operator:
   ```bash
   kubectl apply --server-side -f \
     https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/v1.24/releases/cnpg-1.24.0.yaml
   ```
2. Build a Postgres image that includes **pgvector** (required by
   `sql/001_extensions.sql`) from `ghcr.io/cloudnative-pg/postgresql:16` and push
   as `ghcr.io/sanket/postgres-ha:16-pgvector`.
3. Create the secrets (replace every `REPLACE_ME`):
   `postgres-app-credentials`, `postgres-superuser-credentials`, `backup-aws`,
   plus `sanket-db-url` with the pooler host. See
   [`infra/kubernetes/base/secrets.yaml`](../infra/kubernetes/base/secrets.yaml).

---

## 3. Routine operations

### Check cluster health
```bash
kubectl cnpg status postgres -n sanket         # primary, replicas, lag, last backup
kubectl get pooler -n sanket                   # PgBouncer poolers
```

### Trigger an on-demand backup
```bash
kubectl cnpg backup postgres -n sanket
```

### Manual failover / switchover (e.g. before node maintenance)
```bash
kubectl cnpg promote postgres <replica-pod> -n sanket
```

---

## 4. Backup validation (automated)

Two CronJobs in
[`infra/cron/backup-validation-cronjob.yaml`](../infra/cron/backup-validation-cronjob.yaml):

| Job | Cadence | What it proves |
|-----|---------|----------------|
| `postgres-backup-freshness-check` | daily 03:30 UTC | newest base backup < 26h old **and** WAL archiving is continuous |
| `postgres-backup-restore-drill`   | weekly Sun 05:00 UTC | the backup **actually restores**: restores latest base + replays WAL, runs `pg_verifybackup`, asserts `tenants` non-empty and FORCE RLS intact |

Failures surface as failed K8s Jobs and fire **`SanketBackupValidationFailing`**
(critical) and **`SanketBackupStale`** in Prometheus
([`infra/prometheus/alerts.yml`](../infra/prometheus/alerts.yml)).

> A backup that has never been restored is not a backup. The weekly restore
> drill is what lets us *claim* an RTO with a straight face — its runtime is the
> measured RTO.

---

## 5. Point-in-time recovery (PITR) — incident procedure

Use when data was lost/corrupted at a known time (bad migration, bad bulk write,
accidental delete) and you must roll the database back to just before it.

> ⚠️ PITR creates a **new** cluster from the object store; it does not mutate the
> running one. Decide explicitly whether to cut traffic over to the recovered
> cluster or extract specific rows from it.

1. **Identify the target time** (UTC), just before the bad event:
   `RECOVERY_TARGET="2026-06-14 14:32:00+00"`.

2. **Create a recovery cluster** from the object store (do not delete the
   existing one). Apply a `Cluster` with a `bootstrap.recovery` block:
   ```yaml
   apiVersion: postgresql.cnpg.io/v1
   kind: Cluster
   metadata: { name: postgres-pitr, namespace: sanket }
   spec:
     instances: 1
     imageName: ghcr.io/sanket/postgres-ha:16-pgvector
     storage: { size: 50Gi }
     superuserSecret: { name: postgres-superuser-credentials }
     bootstrap:
       recovery:
         source: postgres
         recoveryTarget:
           targetTime: "2026-06-14 14:32:00+00"
     externalClusters:
       - name: postgres
         barmanObjectStore:
           destinationPath: s3://sanket-backups/postgres-ha
           s3Credentials:
             accessKeyId:     { name: backup-aws, key: access_key_id }
             secretAccessKey: { name: backup-aws, key: secret_access_key }
   ```
   ```bash
   kubectl apply -f postgres-pitr.yaml
   kubectl cnpg status postgres-pitr -n sanket   # wait until recovery completes
   ```

3. **Verify** the recovered data:
   ```bash
   kubectl cnpg psql postgres-pitr -n sanket -- -d sanket \
     -c "SELECT count(*) FROM tenants;"
   ```

4. **Cut over** (full DR) — point `sanket-db-url` / the poolers at the recovered
   cluster, or rename: scale the app to 0, repoint `DATABASE_URL` to
   `postgres-pitr-rw`, run a fresh pooler against it, scale back up. **Or**
   (surgical) `pg_dump`/`COPY` the specific recovered rows back into the live DB.

5. **Post-incident:** once verified, promote the PITR cluster to be the new
   `postgres` (or migrate data back), then delete the temporary cluster and file
   a postmortem.

---

## 6. Failure-mode quick reference

| Symptom | Alert | Action |
|---|---|---|
| Primary pod gone | (auto) | CNPG auto-promotes a standby; verify with `kubectl cnpg status`. No action unless it doesn't recover. |
| Replica lag climbing | `SanketPostgresReplicationLagHigh` | Check replica node I/O/CPU; a lagging sync replica blocks commits. |
| Only 1 instance healthy | `SanketPostgresNoStandby` (critical) | HA degraded — investigate immediately; a second failure = outage. |
| No recent backup | `SanketBackupStale` (critical) | Check `ScheduledBackup` + barman object store creds/quota. |
| Restore drill failed | `SanketBackupValidationFailing` (critical) | Inspect Job logs — backups may be unrestorable. Treat as P1. |
| Connection exhaustion | API 5xx + DB `too many connections` | Check pooler `default_pool_size`; ensure app uses the pooler, not `-rw` directly. |
