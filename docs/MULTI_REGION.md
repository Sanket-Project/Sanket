# SANKET Multi-Region & Data Residency

## Cell model

SANKET runs as independent **regional cells**. Each cell is a full,
self-contained deployment of the stack (postgres + redis + backend + ml-api
+ frontend) bound to a single residency zone:

| Cell           | Residency | Hostname                          |
|----------------|-----------|-----------------------------------|
| `us-east`      | NA        | `us-east.sanket.example`          |
| `us-west`      | NA        | `us-west.sanket.example`          |
| `eu-west`      | EU        | `eu-west.sanket.example`          |
| `eu-central`   | EU        | `eu-central.sanket.example`       |
| `ap-south`     | APAC      | `ap-south.sanket.example`         |
| `ap-northeast` | APAC      | `ap-northeast.sanket.example`     |

A tenant's row lives in **exactly one** cell, recorded in
`tenants.home_region`. Cross-cell data movement is explicitly forbidden — a
GDPR-resident EU tenant's PII, sales, signals, batches, and ML artifacts
never leave the EU cell.

## Request routing

```
                 ┌──────── app.sanket.example ────────┐
                 │  (global control-plane, lightweight)│
                 │  • marketing                        │
                 │  • /api/v1/regions                  │
                 │  • /api/v1/auth/login → resolves     │
                 │    tenant_slug → home_region        │
                 │    and 302s to the cell host        │
                 └────────┬─────────┬──────────────────┘
                          │         │
                 ┌────────┴───┐ ┌───┴────────┐
                 │ us-east cell│ │ eu-west …  │
                 └─────────────┘ └────────────┘
```

The backend's `RegionRouterMiddleware` is a backstop: if a request reaches
the wrong cell after a token has already been issued, we respond
**421 Misdirected Request** with the canonical URL. Smart clients (and
ingress controllers configured with the `421` retry policy) follow it.
Browsers don't natively retry 421, so the SPA reads the JSON body and
performs a hard navigation.

## Onboarding a tenant in a specific region

```sql
INSERT INTO tenants (slug, display_name, tier, status,
                     industries, active_industry,
                     home_region, residency_zone)
VALUES ('acme-eu', 'Acme Europe', 'scale', 'active',
        ARRAY['fashion']::industry_code[], 'fashion',
        'eu-west', 'EU');
```

After this insert, all requests for `acme-eu` must hit `eu-west.sanket.example`.
The control-plane `/auth/login` endpoint consults `tenants.home_region`
on every login and redirects.

## Disaster recovery

| Tier | Mechanism | RPO | RTO |
|------|-----------|----:|----:|
| Postgres | WAL streaming → S3 + nightly base backup (see `infra/cron/backup-cronjob.yaml`) | ~5min | ~30min |
| ML artifacts | PVC volume snapshots (daily) | 24h | ~1h |
| Redis | Stateless — rebuild on restart | n/a | n/a |
| Config / k8s manifests | Git (this repo) | 0 | minutes |

**Cell failover** (rare, e.g. AZ-wide outage):
1. DNS update: point `<cell>.sanket.example` → standby cell IP
2. Restore most recent PITR base + WAL → standby postgres
3. Re-apply k8s overlay in standby region
4. Validate `/health` on all three services + a sentinel `/forecast` call
5. Once validated, update `tenants.home_region` rows to standby cell code
   so middleware no longer issues 421s

A documented full-cell DR rehearsal is performed quarterly.

## Cross-region operations

The only operations that legitimately cross cells:
- **Marketing site / login redirector** — global, no PII
- **Billing webhooks from Razorpay** — Razorpay webhook hits the cell that
  registered the customer (encoded in `notes.tenant_id` on the Razorpay
  customer); routing decisions happen at the ingress
- **Aggregate metrics** — Prometheus federation pulls anonymized counters,
  never per-tenant rows

## Adding a new region

1. Provision postgres + redis in the target cloud region
2. `kubectl apply -k infra/kubernetes/overlays/<new-region>`
3. Insert the row into the `regions` table on the control-plane DB
4. Add an entry in DNS for `<region>.sanket.example` → cell ingress IP
5. Annotate the Razorpay customer notes key so Razorpay webhooks land here
6. Update the marketing site's region picker
