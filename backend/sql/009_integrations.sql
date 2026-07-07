-- SANKET Platform — Integration connections (Shopify, etc.)
-- Requires 002_schema.sql + 003_rls_policies.sql to have been applied first.
--
-- Stores a per-tenant link to an external data source. The access token is
-- encrypted at rest by the application (app.core.crypto) before it is written
-- here; this table never sees the plaintext token.
--
-- Apply:
--   docker exec -i newfolder-postgres-1 psql -U sanket_app -d sanket < backend/sql/009_integrations.sql

CREATE TABLE IF NOT EXISTS integration_connections (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    provider                TEXT            NOT NULL,
    status                  TEXT            NOT NULL DEFAULT 'disconnected',
    shop_domain             TEXT,
    access_token_encrypted  TEXT,
    target_industry         industry_code   NOT NULL,
    last_sync_at            TIMESTAMPTZ,
    last_sync_status        TEXT,
    last_sync_stats         JSONB           NOT NULL DEFAULT '{}',
    error_message           TEXT,
    state                   JSONB           NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    -- One connection per provider per tenant (MVP).
    CONSTRAINT uq_integration_tenant_provider UNIQUE (tenant_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_integration_tenant ON integration_connections (tenant_id);

CREATE TRIGGER trg_integration_connections_updated_at
    BEFORE UPDATE ON integration_connections
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Row-level security ──────────────────────────────────────────────────────
ALTER TABLE integration_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY integration_connections_isolation ON integration_connections
    USING (bypass_rls() OR tenant_id = current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON integration_connections TO sanket_app;
