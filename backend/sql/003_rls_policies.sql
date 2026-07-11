-- SANKET Platform — Row-Level Security Policies
-- Requires 002_schema.sql to have been applied first.
-- These policies restrict all tenant-scoped table access to the current tenant
-- set via: SET LOCAL app.current_tenant_id = '<uuid>'

-- ─────────────────────────────────────────
-- Helper functions: extract current tenant UUID and check RLS bypass
-- ─────────────────────────────────────────

CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS UUID
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID;
$$;

CREATE OR REPLACE FUNCTION bypass_rls() RETURNS BOOLEAN
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT COALESCE(current_setting('app.bypass_rls', TRUE) = 'true', FALSE);
$$;

-- ─────────────────────────────────────────
-- Enable RLS on all tenant-scoped tables
-- ─────────────────────────────────────────

ALTER TABLE tenants             ENABLE ROW LEVEL SECURITY;
ALTER TABLE users               ENABLE ROW LEVEL SECURITY;
ALTER TABLE industry_profiles   ENABLE ROW LEVEL SECURITY;
ALTER TABLE products            ENABLE ROW LEVEL SECURITY;
ALTER TABLE skus                ENABLE ROW LEVEL SECURITY;
ALTER TABLE historical_sales    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pharma_batches      ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_signals    ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_clusters     ENABLE ROW LEVEL SECURITY;
ALTER TABLE forecast_runs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE forecast_results    ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log           ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens      ENABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────
-- TENANTS — read own row only
-- ─────────────────────────────────────────

CREATE POLICY tenants_isolation ON tenants
    USING (bypass_rls() OR id = current_tenant_id());

-- ─────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────

CREATE POLICY users_isolation ON users
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- INDUSTRY PROFILES
-- ─────────────────────────────────────────

CREATE POLICY industry_profiles_isolation ON industry_profiles
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- PRODUCTS
-- ─────────────────────────────────────────

CREATE POLICY products_isolation ON products
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- SKUS
-- ─────────────────────────────────────────

CREATE POLICY skus_isolation ON skus
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- HISTORICAL SALES
-- ─────────────────────────────────────────

CREATE POLICY historical_sales_isolation ON historical_sales
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- PHARMA BATCHES
-- ─────────────────────────────────────────

CREATE POLICY pharma_batches_isolation ON pharma_batches
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- EXTERNAL SIGNALS
-- ─────────────────────────────────────────

CREATE POLICY external_signals_isolation ON external_signals
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- SIGNAL CLUSTERS
-- ─────────────────────────────────────────

CREATE POLICY signal_clusters_isolation ON signal_clusters
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- FORECAST RUNS
-- ─────────────────────────────────────────

CREATE POLICY forecast_runs_isolation ON forecast_runs
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- FORECAST RESULTS
-- ─────────────────────────────────────────

CREATE POLICY forecast_results_isolation ON forecast_results
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- AUDIT LOG
-- ─────────────────────────────────────────

CREATE POLICY audit_log_isolation ON audit_log
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- REFRESH TOKENS
-- ─────────────────────────────────────────

CREATE POLICY refresh_tokens_isolation ON refresh_tokens
    USING (bypass_rls() OR tenant_id = current_tenant_id());

-- ─────────────────────────────────────────
-- Application role: all access goes through this role
-- The app connects as "sanket_app" — never as superuser.
--
-- CRITICAL: row-level security is bypassed for superusers and for BYPASSRLS
-- roles regardless of FORCE ROW LEVEL SECURITY. The runtime role MUST therefore
-- be NOSUPERUSER NOBYPASSRLS or tenant isolation silently does not apply. We
-- create it explicitly with those attributes and a dev-only password (override
-- in every non-local environment via the provisioned secret).
-- ─────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
        CREATE ROLE sanket_app LOGIN PASSWORD 'changeme'
            NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    ELSIF current_user <> 'sanket_app' THEN
        -- Harden an existing role, but never downgrade ourselves mid-script
        -- (would strip the privileges needed to finish applying this file).
        ALTER ROLE sanket_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END;
$$;

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sanket_app', current_database());
END;
$$;

GRANT USAGE ON SCHEMA public TO sanket_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    tenants,
    users,
    industry_profiles,
    products,
    skus,
    external_signals,
    signal_clusters,
    forecast_runs,
    refresh_tokens,
    pharma_batches
TO sanket_app;

GRANT SELECT, INSERT ON
    historical_sales,
    forecast_results,
    audit_log
TO sanket_app;

GRANT SELECT ON industries TO sanket_app;

-- Read access to Alembic's bookkeeping table so the app's startup
-- migration-drift check can run as sanket_app instead of silently failing on
-- InsufficientPrivilege. Guarded: alembic_version only exists once migrations
-- have stamped the database. (Kept in sync by migration 0013 for existing DBs.)
DO $$
BEGIN
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        GRANT SELECT ON alembic_version TO sanket_app;
    END IF;
END;
$$;

GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO sanket_app;

-- Allow sanket_app to SET LOCAL session parameters (required for RLS)
ALTER ROLE sanket_app SET search_path TO public;
