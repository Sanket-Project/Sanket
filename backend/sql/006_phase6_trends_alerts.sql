-- SANKET Phase 6 — Trend Signals, Hybrid Forecast Outputs, Shortage Alerts
-- Requires 002_schema.sql + 003_rls_policies.sql to be applied first.

-- ─────────────────────────────────────────
-- ENUMS
-- ─────────────────────────────────────────

CREATE TYPE trend_signal_source AS ENUM (
    'fred',           -- Federal Reserve Economic Data
    'google_trends',  -- Google Trends search volume
    'reddit',         -- Reddit sentiment via PRAW
    'twitter',        -- Twitter/X (placeholder, future)
    'news_api',       -- News API aggregator (placeholder)
    'rss',            -- RSS feeds
    'pinterest',      -- Pinterest trends
    'tiktok',         -- TikTok trends
    'instagram',      -- Instagram buzz
    'weather',        -- Weather connector
    'competitor_price',-- Competitor price connector
    'fda',            -- FDA regulatory connector
    'logistics',      -- Logistics routing connector
    'synthetic'       -- Fallback random-walk for demo
);

CREATE TYPE trend_signal_kind AS ENUM (
    'economic_indicator',
    'social_buzz',
    'search_interest',
    'news_sentiment',
    'commodity_price'
);

CREATE TYPE alert_severity AS ENUM (
    'info',
    'warning',
    'critical'
);

CREATE TYPE alert_status AS ENUM (
    'open',
    'acknowledged',
    'resolved',
    'suppressed'
);

-- ─────────────────────────────────────────
-- TREND_SIGNALS — raw + normalized signal samples
-- ─────────────────────────────────────────
-- Partitioned by month on captured_at for retention.

CREATE TABLE trend_signals (
    id              UUID NOT NULL DEFAULT uuid_generate_v4(),
    tenant_id       UUID,                       -- nullable: global signals visible to all tenants
    industry        industry_code NOT NULL,
    source          trend_signal_source NOT NULL,
    kind            trend_signal_kind NOT NULL,
    series_key      TEXT NOT NULL,              -- e.g. 'CPIAUCSL', 'google:winter_jacket', 'reddit:r/sneakers'
    category_tags   TEXT[] NOT NULL DEFAULT '{}',
    sku_tags        TEXT[] NOT NULL DEFAULT '{}',
    region          TEXT,
    raw_value       NUMERIC(18, 6),             -- raw measurement (CPI index, search volume 0-100, etc.)
    normalized_score NUMERIC(6, 4) NOT NULL,    -- [-1.0, +1.0] after normalization
    confidence      NUMERIC(5, 4) NOT NULL DEFAULT 1.0, -- [0, 1] source-supplied confidence
    captured_at     TIMESTAMPTZ NOT NULL,       -- when this observation is for
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (id, captured_at)
) PARTITION BY RANGE (captured_at);

-- Initial monthly partitions (will be expanded by retention job)
CREATE TABLE trend_signals_2026_05 PARTITION OF trend_signals
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE trend_signals_2026_06 PARTITION OF trend_signals
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE trend_signals_2026_07 PARTITION OF trend_signals
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE trend_signals_2026_08 PARTITION OF trend_signals
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE INDEX idx_trend_signals_industry_capture
    ON trend_signals (industry, captured_at DESC);
CREATE INDEX idx_trend_signals_source_series
    ON trend_signals (source, series_key, captured_at DESC);
CREATE INDEX idx_trend_signals_tenant
    ON trend_signals (tenant_id, industry, captured_at DESC)
    WHERE tenant_id IS NOT NULL;
CREATE INDEX idx_trend_signals_category_tags
    ON trend_signals USING GIN (category_tags);

COMMENT ON TABLE trend_signals IS
    'Real-time external market signals (economic, social, search). normalized_score is the platform-unified [-1,1] momentum metric.';

-- ─────────────────────────────────────────
-- HYBRID_FORECAST_RUNS — links to forecast_runs but stores fusion metadata
-- ─────────────────────────────────────────

CREATE TABLE hybrid_forecast_runs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    industry            industry_code NOT NULL,
    base_run_id         UUID,                   -- references forecast_runs(id) — no FK due to partitioning
    horizon_weeks       INT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    request_params      JSONB NOT NULL DEFAULT '{}'::jsonb,
    trend_score         NUMERIC(6, 4),          -- aggregate signal score used for this run (nullable until completion)
    signal_volatility   NUMERIC(5, 4),
    alpha               NUMERIC(5, 4),          -- trend sensitivity used
    beta                NUMERIC(5, 4),          -- band expansion coefficient used
    scenarios           JSONB NOT NULL DEFAULT '{}'::jsonb,
    drivers             JSONB NOT NULL DEFAULT '[]'::jsonb,
    result              JSONB,
    error               TEXT,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_hybrid_runs_tenant_industry
    ON hybrid_forecast_runs (tenant_id, industry, created_at DESC);

CREATE INDEX idx_hybrid_runs_tenant_status
    ON hybrid_forecast_runs (tenant_id, status);

-- ─────────────────────────────────────────
-- ALERT_RULES — per-tenant configurable thresholds
-- ─────────────────────────────────────────

CREATE TABLE alert_rules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    industry            industry_code NOT NULL,
    rule_name           TEXT NOT NULL,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    warn_coverage_days  NUMERIC(6, 2) NOT NULL,  -- days of inventory before WARN
    critical_coverage_days NUMERIC(6, 2) NOT NULL,
    trend_weight        NUMERIC(5, 4) NOT NULL DEFAULT 0.30,  -- how much external trend drives risk
    p90_weight          NUMERIC(5, 4) NOT NULL DEFAULT 0.40,  -- upper-band demand weight
    inventory_weight    NUMERIC(5, 4) NOT NULL DEFAULT 0.30,
    cooldown_minutes    INT NOT NULL DEFAULT 60,             -- minimum gap between alerts on same SKU
    notify_webhook      BOOLEAN NOT NULL DEFAULT TRUE,
    notify_websocket    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, industry, rule_name)
);

CREATE TRIGGER trg_alert_rules_updated
    BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- SHORTAGE_ALERTS — append-mostly alert log
-- ─────────────────────────────────────────

CREATE TABLE shortage_alerts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    industry            industry_code NOT NULL,
    sku_id              UUID,                              -- nullable: portfolio-level alerts
    rule_id             UUID REFERENCES alert_rules(id),
    severity            alert_severity NOT NULL,
    status              alert_status NOT NULL DEFAULT 'open',
    risk_score          NUMERIC(6, 4) NOT NULL,            -- 0..1 composite score
    coverage_days       NUMERIC(7, 2),                     -- inventory_on_hand / forecast_daily_demand
    p10_demand          NUMERIC(14, 2),
    p50_demand          NUMERIC(14, 2),
    p90_demand          NUMERIC(14, 2),
    trend_score         NUMERIC(6, 4),
    drivers             JSONB NOT NULL DEFAULT '[]'::jsonb, -- ranked list of contributing signals
    title               TEXT NOT NULL,
    message             TEXT NOT NULL,
    fired_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_by     UUID REFERENCES users(id),
    acknowledged_at     TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    resolution_note     TEXT
);

CREATE INDEX idx_alerts_tenant_status_fired
    ON shortage_alerts (tenant_id, status, fired_at DESC);
CREATE INDEX idx_alerts_industry_severity
    ON shortage_alerts (industry, severity, fired_at DESC);
CREATE INDEX idx_alerts_sku
    ON shortage_alerts (sku_id, fired_at DESC) WHERE sku_id IS NOT NULL;

-- ─────────────────────────────────────────
-- ROW-LEVEL SECURITY
-- ─────────────────────────────────────────

ALTER TABLE trend_signals      ENABLE ROW LEVEL SECURITY;
ALTER TABLE hybrid_forecast_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rules        ENABLE ROW LEVEL SECURITY;
ALTER TABLE shortage_alerts    ENABLE ROW LEVEL SECURITY;

-- trend_signals: tenant signals OR global (tenant_id IS NULL) are visible
CREATE POLICY trend_signals_select ON trend_signals
    FOR SELECT TO sanket_app
    USING (
        bypass_rls()
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    );

CREATE POLICY trend_signals_modify ON trend_signals
    FOR ALL TO sanket_app
    USING (
        bypass_rls()
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    )
    WITH CHECK (
        bypass_rls()
        OR tenant_id IS NULL
        OR tenant_id = current_tenant_id()
    );

CREATE POLICY hybrid_runs_tenant ON hybrid_forecast_runs
    FOR ALL TO sanket_app
    USING (bypass_rls() OR tenant_id = current_tenant_id())
    WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());

CREATE POLICY alert_rules_tenant ON alert_rules
    FOR ALL TO sanket_app
    USING (bypass_rls() OR tenant_id = current_tenant_id())
    WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());

CREATE POLICY shortage_alerts_tenant ON shortage_alerts
    FOR ALL TO sanket_app
    USING (bypass_rls() OR tenant_id = current_tenant_id())
    WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON trend_signals, hybrid_forecast_runs, alert_rules, shortage_alerts TO sanket_app;


-- ─────────────────────────────────────────
-- DEFAULT ALERT RULE SEEDS (per industry, applied to demo tenant)
-- ─────────────────────────────────────────
-- These are templates; new tenants get a clone via app/services/alerts/defaults.py.

COMMENT ON TABLE shortage_alerts IS
    'Cross-industry supply shortage alerts fused from inventory position, probabilistic demand, and external trend momentum.';
