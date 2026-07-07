# SANKET Production Promotion & Deployment Checklist

This document outlines the mandatory security, database, and operational steps required to deploy the SANKET FastAPI backend to a production environment. 

---

## 1. Secret Rotation Steps

Several developer-tier and development-phase secrets were exposed on disk and must be rotated before promoting the application to production.

### A. Supabase Database Password
- **Action**: Rotate the database password.
- **Where**: Supabase Dashboard → Project Settings → Database → Reset database password.
- **Note**: The new password must be long, random, and not reuse the development password (`Iphone@17pro`).

### B. Firebase Service Account & Web API Keys
- **Action**: Revoke the compromised development key and generate a fresh one.
- **Where**: 
  1. GCP Console → IAM & Admin → Service Accounts → Select the `firebase-adminsdk` service account.
  2. Under the **Keys** tab, locate key ID `0d2d068d8b768e1d3db9607645cf90c9277d964a` and click **Delete**.
  3. Click **Add Key** → **Create new key** (JSON format) to generate a fresh service account key file.
- **Razorpay Keys**: Mark the development keys (`rzp_test_T0L0EvzhRrTQnb`) as compromised and generate fresh production keys in the Razorpay Dashboard.

### C. JWT Secret & Other Tokens
- **Action**: Generate fresh, random 32-byte hex keys for JWT authentication and ML communication.
- **Commands**:
  ```bash
  # Generate JWT_SECRET
  openssl rand -hex 32

  # Generate ML_SERVICE_TOKEN (Must be identical in backend and ml-api)
  openssl rand -hex 32

  # Generate METRICS_TOKEN (Used to protect /metrics)
  openssl rand -hex 32

  # Generate OPS_HEALTH_TOKEN (Used to protect /health/detailed)
  openssl rand -hex 32
  ```

---

## 2. Git History Audit for Leaked Keys

A plaintext Firebase service-account key was previously tracked on disk. Verify that it was never committed to Git history.

- **Action**: Run the following command from the root of the repository to check if `backend/firebase-credentials.json` exists in any historical commits:
  ```bash
  git log --all --full-history -- 'backend/firebase-credentials.json'
  ```
- **If commits are returned**: The repository history is compromised. You must purge the file from history using `git filter-repo` or BFG Repo Cleaner before pushing to a public repository:
  ```bash
  git filter-repo --path backend/firebase-credentials.json --invert-paths
  ```

---

## 3. Database Role Hardening & Verification

In production, row-level security (RLS) is bypassable if the app connects using a superuser account (like `postgres`). The backend contains a startup guard that checks role attributes and aborts boot if the credentials bypass RLS.

### A. Create and Configure `sanket_app` Role
Run the following SQL commands as the superuser/admin role (once per database):

```sql
-- Create the role with login permissions but stripped of RLS-bypass attributes
CREATE ROLE sanket_app WITH LOGIN PASSWORD '<YOUR_STRONG_ROTATED_PASSWORD>'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

-- Grant usage on schemas
GRANT USAGE ON SCHEMA public TO sanket_app;

-- Grant permissions on tables (handled by migrations but good to ensure)
GRANT SELECT, INSERT, UPDATE, DELETE ON
    tenants, users, industry_profiles, products, skus, external_signals,
    signal_clusters, forecast_runs, refresh_tokens, pharma_batches,
    subscriptions, webhook_endpoints, webhook_deliveries
TO sanket_app;

GRANT SELECT, INSERT ON historical_sales, forecast_results, audit_log, usage_events, usage_rollups_daily TO sanket_app;
GRANT SELECT ON plans, regions TO sanket_app;
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq, webhook_deliveries_id_seq, usage_events_id_seq TO sanket_app;
```

### B. Verify RLS Hardening Attributes
Run this query to check if the role is properly restricted:

```sql
SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'sanket_app';
```

- **Expected Output**:
  | rolsuper | rolbypassrls |
  |----------|--------------|
  | f        | f            |

> [!IMPORTANT]
> If either column returns `t` (true), the role can bypass tenant isolation. The startup guard **will fail**, preventing the container from starting.

---

## 4. Environment Variables & Deployment Configuration

Inject the following environment variables into the production runtime environment (Kubernetes base/secrets, Cloud Run, etc.).

### A. Firebase Workload Identity / Credentials
Instead of using a filesystem path, inject the service account JSON as a base64-encoded string:
- **Command**:
  ```bash
  base64 -w0 backend/firebase-credentials.json
  ```
- **Env Var**:
  ```env
  FIREBASE_CREDENTIALS_JSON="<BASE64_ENCODED_OUTPUT>"
  ```

### B. Trusted Proxy Config (`FORWARDED_ALLOW_IPS`)
Uvicorn must only trust headers (like `X-Forwarded-For`) from the load balancer CIDR to prevent IP-spoofing rate-limit bypasses.
- **Action**: Set `FORWARDED_ALLOW_IPS` to the IP ranges of your load balancer.
- **Example (GCP HTTP(S) Load Balancer)**:
  ```env
  FORWARDED_ALLOW_IPS="130.211.0.0/22,35.191.0.0/16"
  ```

### C. Grafana Security
- **Action**: Disable anonymous access and enforce a strong admin password in `docker-compose.yml` or your dashboard environment.
- **Env Var**:
  ```env
  GRAFANA_PASSWORD="<STRONG_ADMIN_PASSWORD>"
  ```

### D. Observability & Prometheus Scraping
Because `/metrics` is protected by `METRICS_TOKEN` in production, you must update your Prometheus scraping configuration.
- **Scrape Config Example**:
  ```yaml
  scrape_configs:
    - job_name: 'sanket-backend'
      metrics_path: '/metrics'
      authorization:
        credentials: '<METRICS_TOKEN>'
      static_configs:
        - targets: ['backend-service:8000']
  ```
