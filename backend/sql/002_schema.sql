-- SANKET Platform — Core Schema
-- Requires 001_extensions.sql to have been applied first.

-- ─────────────────────────────────────────
-- ENUM TYPES
-- ─────────────────────────────────────────

CREATE TYPE industry_code AS ENUM (
    'fashion',
    'electronics',
    'pharma',
    'agrocenter',
    'hardware'
);

CREATE TYPE tenant_tier AS ENUM (
    'growth',
    'scale',
    'enterprise'
);

CREATE TYPE tenant_status AS ENUM (
    'trial',
    'active',
    'suspended',
    'cancelled'
);

CREATE TYPE user_role AS ENUM (
    'owner',
    'admin',
    'analyst',
    'viewer',
    'api_service'
);

CREATE TYPE product_status AS ENUM (
    'active',
    'discontinued',
    'seasonal',
    'clearance',
    'pre_launch'
);

CREATE TYPE signal_type AS ENUM (
    'weather',
    'trend_search',
    'social_sentiment',
    'competitor_price',
    'macro_economic',
    'regulatory',
    'supplier_lead',
    'logistics_disruption'
);

CREATE TYPE signal_status AS ENUM (
    'pending',
    'validated',
    'rejected',
    'expired'
);

CREATE TYPE gxp_batch_status AS ENUM (
    'quarantine',
    'released',
    'rejected',
    'recalled',
    'expired'
);

-- ─────────────────────────────────────────
-- HELPER: updated_at trigger function
-- ─────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- ─────────────────────────────────────────
-- INDUSTRIES  (global, non-tenant-scoped)
-- ─────────────────────────────────────────

CREATE TABLE industries (
    code                    industry_code   PRIMARY KEY,
    display_name            TEXT            NOT NULL,
    default_horizon_weeks   SMALLINT        NOT NULL CHECK (default_horizon_weeks > 0),
    granularity_dimensions  TEXT[]          NOT NULL DEFAULT '{}',
    required_signal_types   signal_type[]   NOT NULL DEFAULT '{}',
    sku_attribute_schema    JSONB           NOT NULL DEFAULT '{}',
    forecast_models         TEXT[]          NOT NULL DEFAULT '{}',
    optimization_models     TEXT[]          NOT NULL DEFAULT '{}',
    audit_level             TEXT            NOT NULL DEFAULT 'standard'
                                            CHECK (audit_level IN ('standard','gxp')),
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_industries_updated_at
    BEFORE UPDATE ON industries
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- TENANTS
-- ─────────────────────────────────────────

CREATE TABLE tenants (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                CITEXT          NOT NULL UNIQUE,
    display_name        TEXT            NOT NULL,
    tier                tenant_tier     NOT NULL DEFAULT 'growth',
    status              tenant_status   NOT NULL DEFAULT 'trial',
    industries          industry_code[] NOT NULL DEFAULT '{}',
    active_industry     industry_code   NOT NULL,
    max_skus            INTEGER         NOT NULL DEFAULT 10000,
    max_users           SMALLINT        NOT NULL DEFAULT 5,
    data_retention_days SMALLINT        NOT NULL DEFAULT 730,
    settings            JSONB           NOT NULL DEFAULT '{}',
    trial_ends_at       TIMESTAMPTZ,
    contract_ends_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_tenants_status ON tenants (status);
CREATE INDEX idx_tenants_active_industry ON tenants (active_industry);

CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────

CREATE TABLE users (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID        NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    email               CITEXT      NOT NULL,
    -- Firebase UID — join key to the Firebase identity (nullable: backfilled on
    -- first sign-in). Unique so one Firebase user maps to one tenant user.
    firebase_uid        TEXT        UNIQUE,
    -- Nullable: Firebase owns passwords in production; retained only for the
    -- local dev-login fallback (Argon2-verified).
    password_hash       TEXT,
    full_name           TEXT        NOT NULL,
    role                user_role   NOT NULL DEFAULT 'analyst',
    active_industry     industry_code NOT NULL,
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    last_login_at       TIMESTAMPTZ,
    mfa_secret          TEXT,
    mfa_enabled         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_tenant_email UNIQUE (tenant_id, email)
);

CREATE INDEX idx_users_tenant_id ON users (tenant_id);
CREATE INDEX idx_users_email ON users USING gin (email gin_trgm_ops);
CREATE INDEX idx_users_active_industry ON users (tenant_id, active_industry);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- INDUSTRY PROFILES  (per-tenant overrides)
-- ─────────────────────────────────────────

CREATE TABLE industry_profiles (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    industry                industry_code   NOT NULL,
    custom_horizon_weeks    SMALLINT        CHECK (custom_horizon_weeks > 0),
    custom_signal_types     signal_type[]   NOT NULL DEFAULT '{}',
    model_overrides         JSONB           NOT NULL DEFAULT '{}',
    feature_flags           JSONB           NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_industry_profiles_tenant_industry UNIQUE (tenant_id, industry)
);

CREATE INDEX idx_industry_profiles_tenant_id ON industry_profiles (tenant_id);

CREATE TRIGGER trg_industry_profiles_updated_at
    BEFORE UPDATE ON industry_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- PRODUCTS
-- ─────────────────────────────────────────

CREATE TABLE products (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    industry        industry_code   NOT NULL,
    external_id     TEXT,
    name            TEXT            NOT NULL,
    brand           TEXT,
    category        TEXT            NOT NULL,
    subcategory     TEXT,
    status          product_status  NOT NULL DEFAULT 'active',
    attributes      JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_products_tenant_id ON products (tenant_id);
CREATE INDEX idx_products_industry ON products (tenant_id, industry);
CREATE INDEX idx_products_category ON products (tenant_id, category, subcategory);
CREATE INDEX idx_products_attributes ON products USING gin (attributes jsonb_path_ops);
CREATE INDEX idx_products_name_trgm ON products USING gin (name gin_trgm_ops);
CREATE UNIQUE INDEX uq_products_tenant_external
    ON products (tenant_id, external_id)
    WHERE external_id IS NOT NULL;

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- SKUS
-- ─────────────────────────────────────────

CREATE TABLE skus (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    product_id      UUID            NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    industry        industry_code   NOT NULL,
    sku_code        TEXT            NOT NULL,
    external_id     TEXT,
    gtin            TEXT,
    description     TEXT,
    unit_cost       NUMERIC(18,4),
    unit_price      NUMERIC(18,4),
    currency        CHAR(3)         NOT NULL DEFAULT 'USD',
    lead_time_days  SMALLINT,
    moq             INTEGER         DEFAULT 1,
    safety_stock    INTEGER         DEFAULT 0,
    reorder_point   INTEGER         DEFAULT 0,
    attributes      JSONB           NOT NULL DEFAULT '{}',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_skus_tenant_sku_code UNIQUE (tenant_id, sku_code)
);

CREATE INDEX idx_skus_tenant_id ON skus (tenant_id);
CREATE INDEX idx_skus_product_id ON skus (product_id);
CREATE INDEX idx_skus_industry ON skus (tenant_id, industry);
CREATE INDEX idx_skus_attributes ON skus USING gin (attributes jsonb_path_ops);
CREATE UNIQUE INDEX uq_skus_tenant_external
    ON skus (tenant_id, external_id)
    WHERE external_id IS NOT NULL;
CREATE UNIQUE INDEX uq_skus_tenant_gtin
    ON skus (tenant_id, gtin)
    WHERE gtin IS NOT NULL;

CREATE TRIGGER trg_skus_updated_at
    BEFORE UPDATE ON skus
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- HISTORICAL SALES  (range-partitioned)
-- ─────────────────────────────────────────

CREATE TABLE historical_sales (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL,
    sku_id          UUID            NOT NULL,
    industry        industry_code   NOT NULL,
    sale_time       TIMESTAMPTZ     NOT NULL,
    channel         TEXT            NOT NULL DEFAULT 'unknown',
    region          TEXT,
    units_sold      INTEGER         NOT NULL CHECK (units_sold >= 0),
    gross_revenue   NUMERIC(18,4),
    net_revenue     NUMERIC(18,4),
    returns         INTEGER         NOT NULL DEFAULT 0 CHECK (returns >= 0),
    promo_flag      BOOLEAN         NOT NULL DEFAULT FALSE,
    markdown_pct    NUMERIC(5,2)    DEFAULT 0 CHECK (markdown_pct BETWEEN 0 AND 100),
    -- Availability at the time of the record. NULL = unknown (most historical
    -- feeds won't have it); the ML censored-demand correction treats NULL as
    -- in-stock and only unconstrains demand where availability is explicitly
    -- false or (absent any signal) a regular seller shows a suspicious zero.
    in_stock        BOOLEAN,
    metadata        JSONB           NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, sale_time)
) PARTITION BY RANGE (sale_time);

-- Quarterly partitions covering 3 years back and 1 year forward
DO $$
DECLARE
    y   INT;
    q   INT;
    qs  DATE;
    qe  DATE;
BEGIN
    FOR y IN 2022..2027 LOOP
        FOR q IN 1..4 LOOP
            qs := make_date(y, (q-1)*3+1, 1);
            qe := qs + INTERVAL '3 months';
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS historical_sales_%s_q%s
                 PARTITION OF historical_sales
                 FOR VALUES FROM (%L) TO (%L)',
                y, q, qs, qe
            );
        END LOOP;
    END LOOP;
END;
$$;

CREATE INDEX idx_hsales_tenant_sku ON historical_sales (tenant_id, sku_id, sale_time DESC);
CREATE INDEX idx_hsales_tenant_time ON historical_sales (tenant_id, sale_time DESC);
CREATE INDEX idx_hsales_industry ON historical_sales (tenant_id, industry, sale_time DESC);
CREATE INDEX idx_hsales_channel ON historical_sales (tenant_id, channel, sale_time DESC);

-- ─────────────────────────────────────────
-- PHARMA BATCHES  (GxP / 21 CFR Part 11)
-- ─────────────────────────────────────────

CREATE TABLE pharma_batches (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    sku_id              UUID            NOT NULL REFERENCES skus (id) ON DELETE CASCADE,
    lot_number          TEXT            NOT NULL,
    ndc_code            TEXT,
    manufactured_at     DATE            NOT NULL,
    expiry_date         DATE            NOT NULL,
    quantity_produced   INTEGER         NOT NULL CHECK (quantity_produced > 0),
    quantity_remaining  INTEGER         NOT NULL CHECK (quantity_remaining >= 0),
    gxp_status          gxp_batch_status NOT NULL DEFAULT 'quarantine',
    cold_chain_required BOOLEAN         NOT NULL DEFAULT FALSE,
    storage_temp_min_c  NUMERIC(5,2),
    storage_temp_max_c  NUMERIC(5,2),
    qa_released_by      UUID            REFERENCES users (id),
    qa_released_at      TIMESTAMPTZ,
    recall_reason       TEXT,
    recalled_at         TIMESTAMPTZ,
    certificate_url     TEXT,
    metadata            JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_pharma_batch_tenant_lot UNIQUE (tenant_id, sku_id, lot_number),
    CONSTRAINT chk_cold_chain_temps CHECK (
        cold_chain_required = FALSE OR (storage_temp_min_c IS NOT NULL AND storage_temp_max_c IS NOT NULL)
    ),
    CONSTRAINT chk_temp_range CHECK (
        storage_temp_min_c IS NULL OR storage_temp_max_c IS NULL OR storage_temp_min_c < storage_temp_max_c
    ),
    CONSTRAINT chk_expiry_after_manufacture CHECK (expiry_date > manufactured_at),
    CONSTRAINT chk_qty_remaining_lte_produced CHECK (quantity_remaining <= quantity_produced)
);

CREATE INDEX idx_pharma_batches_tenant_id ON pharma_batches (tenant_id);
CREATE INDEX idx_pharma_batches_sku_id ON pharma_batches (sku_id);
CREATE INDEX idx_pharma_batches_expiry ON pharma_batches (tenant_id, expiry_date);
CREATE INDEX idx_pharma_batches_gxp_status ON pharma_batches (tenant_id, gxp_status);

CREATE TRIGGER trg_pharma_batches_updated_at
    BEFORE UPDATE ON pharma_batches
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- EXTERNAL SIGNALS
-- ─────────────────────────────────────────

CREATE TABLE external_signals (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    industry        industry_code   NOT NULL,
    signal_type     signal_type     NOT NULL,
    status          signal_status   NOT NULL DEFAULT 'pending',
    source_name     TEXT            NOT NULL,
    source_url      TEXT,
    effective_at    TIMESTAMPTZ     NOT NULL,
    expires_at      TIMESTAMPTZ,
    region          TEXT,
    category_tags   TEXT[]          NOT NULL DEFAULT '{}',
    sku_tags        TEXT[]          NOT NULL DEFAULT '{}',
    raw_payload     JSONB           NOT NULL DEFAULT '{}',
    processed_value NUMERIC(18,6),
    sentiment_score NUMERIC(5,4)    CHECK (sentiment_score BETWEEN -1.0 AND 1.0),
    impact_weight   NUMERIC(5,4)    CHECK (impact_weight BETWEEN 0.0 AND 1.0),
    validated_by    UUID            REFERENCES users (id),
    validated_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_signals_tenant_type ON external_signals (tenant_id, signal_type, effective_at DESC);
CREATE INDEX idx_signals_tenant_industry ON external_signals (tenant_id, industry, effective_at DESC);
CREATE INDEX idx_signals_status ON external_signals (tenant_id, status);
CREATE INDEX idx_signals_category_tags ON external_signals USING gin (category_tags);
CREATE INDEX idx_signals_sku_tags ON external_signals USING gin (sku_tags);
CREATE INDEX idx_signals_raw_payload ON external_signals USING gin (raw_payload jsonb_path_ops);

CREATE TRIGGER trg_signals_updated_at
    BEFORE UPDATE ON external_signals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- SIGNAL CLUSTERS  (pgvector embeddings)
-- ─────────────────────────────────────────

CREATE TABLE signal_clusters (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    industry            industry_code   NOT NULL,
    cluster_label       TEXT            NOT NULL,
    signal_count        INTEGER         NOT NULL DEFAULT 0,
    centroid_embedding  vector(768)     NOT NULL,
    representative_ids  UUID[]          NOT NULL DEFAULT '{}',
    cohesion_score      NUMERIC(5,4),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_signal_clusters_tenant_industry ON signal_clusters (tenant_id, industry);
CREATE INDEX idx_signal_clusters_hnsw
    ON signal_clusters
    USING hnsw (centroid_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE TRIGGER trg_signal_clusters_updated_at
    BEFORE UPDATE ON signal_clusters
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- FORECAST RUNS
-- ─────────────────────────────────────────

CREATE TABLE forecast_runs (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    industry            industry_code   NOT NULL,
    run_name            TEXT,
    model_stack         TEXT[]          NOT NULL DEFAULT '{}',
    horizon_weeks       SMALLINT        NOT NULL CHECK (horizon_weeks > 0),
    granularity         TEXT            NOT NULL DEFAULT 'weekly',
    filters             JSONB           NOT NULL DEFAULT '{}',
    status              TEXT            NOT NULL DEFAULT 'pending'
                                        CHECK (status IN ('pending','running','completed','failed')),
    triggered_by        UUID            REFERENCES users (id),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    error_message       TEXT,
    metrics             JSONB           NOT NULL DEFAULT '{}',
    artifact_path       TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_forecast_runs_tenant_id ON forecast_runs (tenant_id, created_at DESC);
CREATE INDEX idx_forecast_runs_status ON forecast_runs (tenant_id, status);

CREATE TRIGGER trg_forecast_runs_updated_at
    BEFORE UPDATE ON forecast_runs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- FORECAST RESULTS
-- ─────────────────────────────────────────

CREATE TABLE forecast_results (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    run_id          UUID        NOT NULL REFERENCES forecast_runs (id) ON DELETE CASCADE,
    sku_id          UUID        NOT NULL,
    forecast_date   DATE        NOT NULL,
    p10             NUMERIC(18,4) NOT NULL,
    p50             NUMERIC(18,4) NOT NULL,
    p90             NUMERIC(18,4) NOT NULL,
    model_name      TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, forecast_date)
) PARTITION BY RANGE (forecast_date);

DO $$
DECLARE
    y   INT;
    q   INT;
    qs  DATE;
    qe  DATE;
BEGIN
    FOR y IN 2024..2027 LOOP
        FOR q IN 1..4 LOOP
            qs := make_date(y, (q-1)*3+1, 1);
            qe := qs + INTERVAL '3 months';
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS forecast_results_%s_q%s
                 PARTITION OF forecast_results
                 FOR VALUES FROM (%L) TO (%L)',
                y, q, qs, qe
            );
        END LOOP;
    END LOOP;
END;
$$;

CREATE INDEX idx_fresults_tenant_sku ON forecast_results (tenant_id, sku_id, forecast_date);
CREATE INDEX idx_fresults_run_id ON forecast_results (run_id);

-- ─────────────────────────────────────────
-- AUDIT LOG  (immutable, 21 CFR Part 11)
-- ─────────────────────────────────────────

CREATE TABLE audit_log (
    id              BIGSERIAL       PRIMARY KEY,
    tenant_id       UUID            NOT NULL,
    user_id         UUID,
    industry        industry_code,
    action          TEXT            NOT NULL,
    entity_type     TEXT            NOT NULL,
    entity_id       TEXT,
    old_value       JSONB,
    new_value       JSONB,
    ip_address      INET,
    user_agent      TEXT,
    request_id      TEXT,
    occurred_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_tenant ON audit_log (tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_entity ON audit_log (tenant_id, entity_type, entity_id, occurred_at DESC);
CREATE INDEX idx_audit_user ON audit_log (tenant_id, user_id, occurred_at DESC);
CREATE INDEX idx_audit_action ON audit_log (tenant_id, action, occurred_at DESC);

-- Audit log rows must never be updated or deleted
CREATE OR REPLACE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE OR REPLACE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- ─────────────────────────────────────────
-- REFRESH TOKENS
-- ─────────────────────────────────────────

CREATE TABLE refresh_tokens (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    tenant_id       UUID        NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    token_hash      TEXT        NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens (expires_at) WHERE revoked_at IS NULL;
