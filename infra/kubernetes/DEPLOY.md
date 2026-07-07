# SANKET — Production Deployment (GKE)

Everything runs in **one place**: source + CI/CD + container registry in this
GitHub repo, and one **GKE** cluster hosting backend, frontend, ML inference,
Redis, and an in-cluster HA Postgres (CloudNativePG). Nothing is split across
providers.

```
GitHub (source + Actions + GHCR)
        │  build-images → ghcr.io/sanket-project/{backend,ml-api,frontend}
        │  deploy.yml   → Workload Identity Federation (keyless)
        ▼
GKE cluster (namespace: sanket)
   ├─ backend (3–20 HPA)      ├─ ml-api (isolated, ClusterIP)
   ├─ frontend (nginx)        ├─ redis
   ├─ CloudNativePG (HA + PITR → GCS)   └─ ingress-nginx + cert-manager (TLS)
```

---

## 0. Cluster prerequisites (once)

Create the GKE cluster, then install the operators the manifests assume:

```bash
# nginx ingress controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
# cert-manager (issues the Let's Encrypt TLS cert; base/ingress.yaml references
# ClusterIssuer "letsencrypt-prod" — create it after install)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
# CloudNativePG operator (runs the HA Postgres Cluster in base/postgres.yaml)
kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.0.yaml
```

## 1. Keyless CI → GCP (Workload Identity Federation)

No JSON key lives in GitHub. Create a WIF pool + provider and a deployer SA:

```bash
PROJECT_ID=REPLACE_ME
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
REPO=Sanket-Project/Sanket

gcloud iam service-accounts create gh-deployer \
  --project "$PROJECT_ID" --display-name "GitHub Actions deployer"
SA=gh-deployer@${PROJECT_ID}.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" --role="roles/container.developer"

gcloud iam workload-identity-pools create github --project "$PROJECT_ID" --location=global
gcloud iam workload-identity-pools providers create-oidc github \
  --project "$PROJECT_ID" --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$SA" --project "$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUM}/locations/global/workloadIdentityPools/github/attribute.repository/${REPO}"
```

## 2. GitHub repo Variables (Settings → Secrets and variables → Actions → Variables)

Until these exist, `deploy.yml` **skips with a warning** (pipeline stays green):

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | `sanket-prod-1234` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<num>/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_SERVICE_ACCOUNT` | `gh-deployer@sanket-prod-1234.iam.gserviceaccount.com` |
| `GKE_CLUSTER` | `sanket` |
| `GKE_LOCATION` | `us-central1` (region) or `us-central1-a` (zone) |

Optional **Secret** `GHCR_PULL_TOKEN` (a `read:packages` PAT) — only if you keep
the GHCR packages private. Simpler: make the org packages **public** and skip it.

## 3. Bootstrap cluster secrets (once, out-of-band — never committed)

See `base/secrets.yaml.example` for the full key list.

```bash
kubectl create ns sanket
kubectl -n sanket create secret generic sanket-secrets \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)" \
  --from-literal=JWT_SECRET="$(openssl rand -hex 32)" \
  --from-literal=ML_SERVICE_TOKEN="$(openssl rand -hex 32)"
kubectl -n sanket create secret generic sanket-db-url \
  --from-literal=DATABASE_URL="postgresql+asyncpg://sanket_app:<pw>@postgres-pooler-rw:5432/sanket" \
  --from-literal=DATABASE_URL_DIRECT="postgresql+asyncpg://sanket_app:<pw>@postgres-rw:5432/sanket" \
  --from-literal=ML_DATABASE_URL="postgresql://sanket_app:<pw>@postgres-rw:5432/sanket"
# REQUIRED in production (APP_ENV=production refuses to boot without Firebase):
kubectl -n sanket create secret generic sanket-firebase \
  --from-literal=FIREBASE_PROJECT_ID="<project>" \
  --from-literal=FIREBASE_CREDENTIALS_PATH="/var/run/secrets/firebase/service-account.json" \
  --from-file=service-account.json=./firebase-credentials.json
# Continuous WAL backups → GCS (S3-interop). Enables PITR.
kubectl -n sanket create secret generic backup-aws \
  --from-literal=access_key_id="<hmac-key>" --from-literal=secret_access_key="<hmac-secret>"
```

## 4. Set your real domain

Edit the two `REPLACE_ME` placeholders in
`overlays/production/kustomization.yaml` (Ingress host + `ALLOWED_ORIGINS`) to
your production domain, and point that domain's DNS at the ingress-nginx external IP.

## 5. Deploy

- **Staging** deploys automatically after `build-images` succeeds on `main`.
- **Production** is manual and gated: **Actions → deploy → Run workflow → environment: production**.

The pipeline pins images to the exact commit SHA (`sha-<commit>`), runs the
Alembic migration Job to completion **before** rolling out, waits for rollout,
smoke-tests `/healthz` + `/api/v1/health`, and auto-rolls-back on failure.

**Rollback:** re-run *deploy* (workflow_dispatch) from a previous green commit —
its images are immutable, so the prior state is exactly reproducible.
```
