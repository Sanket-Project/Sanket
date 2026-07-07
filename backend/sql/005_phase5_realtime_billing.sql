-- SANKET Phase 5: real-time + billing/metering + outbound webhooks + multi-region
-- Apply after 003_rls_policies.sql.

-- ─────────────────────────────────────────
-- REGIONS (global)
-- ─────────────────────────────────────────
CREATE TYPE region_code AS ENUM ('us-east', 'us-west', 'eu-west', 'eu-central', 'ap-south', 'ap-northeast');

CREATE TABLE regions (
    code           region_code PRIMARY KEY,
    display_name   TEXT        NOT NULL,
    api_endpoint   TEXT        NOT NULL,
    cell_url       TEXT        NOT NULL,           -- regional control-plane URL
    residency_zone TEXT        NOT NULL,           -- 'NA' | 'EU' | 'APAC'
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO regions VALUES
    ('us-east',      'US East (Virginia)',     'https://us-east.sanket.example/api/v1',  'https://us-east.sanket.example',  'NA',   TRUE),
    ('us-west',      'US West (Oregon)',       'https://us-west.sanket.example/api/v1',  'https://us-west.sanket.example',  'NA',   TRUE),
    ('eu-west',      'EU West (Ireland)',      'https://eu-west.sanket.example/api/v1',  'https://eu-west.sanket.example',  'EU',   TRUE),
    ('eu-central',   'EU Central (Frankfurt)', 'https://eu-central.sanket.example/api/v1','https://eu-central.sanket.example','EU',  TRUE),
    ('ap-south',     'AP South (Mumbai)',      'https://ap-south.sanket.example/api/v1', 'https://ap-south.sanket.example',  'APAC', TRUE),
    ('ap-northeast', 'AP Northeast (Tokyo)',   'https://ap-northeast.sanket.example/api/v1','https://ap-northeast.sanket.example','APAC', TRUE)
ON CONFLICT (code) DO NOTHING;

-- ─────────────────────────────────────────
-- Tenant: residency region (added without breaking existing rows)
-- ─────────────────────────────────────────
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS home_region    region_code NOT NULL DEFAULT 'us-east',
    ADD COLUMN IF NOT EXISTS residency_zone TEXT        NOT NULL DEFAULT 'NA' CHECK (residency_zone IN ('NA','EU','APAC'));

CREATE INDEX IF NOT EXISTS idx_tenants_home_region ON tenants (home_region);

-- ─────────────────────────────────────────
-- BILLING
-- ─────────────────────────────────────────
CREATE TYPE subscription_status AS ENUM (
    'trialing','active','past_due','paused','cancelled','incomplete'
);

CREATE TYPE meter_kind AS ENUM (
    'api_request','forecast_row','training_minute','signal_ingest','active_sku','user_seat'
);

CREATE TABLE plans (
    id                  TEXT        PRIMARY KEY,            -- e.g. "growth_monthly"
    display_name        TEXT        NOT NULL,
    tier                tenant_tier NOT NULL,
    base_price_cents    INTEGER     NOT NULL,
    billing_interval    TEXT        NOT NULL DEFAULT 'month' CHECK (billing_interval IN ('month','year')),
    razorpay_plan_id    TEXT,
    included_quotas     JSONB       NOT NULL DEFAULT '{}',  -- {forecast_row: 1000000, ...}
    overage_rates_cents JSONB       NOT NULL DEFAULT '{}',  -- {forecast_row: 1, ...}
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO plans (id, display_name, tier, base_price_cents, billing_interval, included_quotas, overage_rates_cents) VALUES
    ('growth_monthly',     'Growth',     'growth',     499500, 'month',
     '{"forecast_row": 250000,  "training_minute": 60,  "active_sku": 10000,   "user_seat": 5}',
     '{"forecast_row": 5,       "training_minute": 50,  "active_sku": 10,      "user_seat": 5000}'),
    ('scale_monthly',      'Scale',      'scale',      1499500, 'month',
     '{"forecast_row": 2000000, "training_minute": 300, "active_sku": 100000,  "user_seat": 25}',
     '{"forecast_row": 3,       "training_minute": 30,  "active_sku": 5,       "user_seat": 4000}'),
    ('growth_yearly',      'Growth Yearly', 'growth',  4995000, 'year',
     '{"forecast_row": 250000,  "training_minute": 60,  "active_sku": 10000,   "user_seat": 5}',
     '{"forecast_row": 5,       "training_minute": 50,  "active_sku": 10,      "user_seat": 5000}'),
    ('scale_yearly',       'Scale Yearly',  'scale',   14995000, 'year',
     '{"forecast_row": 2000000, "training_minute": 300, "active_sku": 100000,  "user_seat": 25}',
     '{"forecast_row": 3,       "training_minute": 30,  "active_sku": 5,       "user_seat": 4000}'),
    ('enterprise_monthly', 'Enterprise', 'enterprise', 0, 'month',
     '{"forecast_row": 999999999, "training_minute": 99999, "active_sku": 999999999, "user_seat": 9999}',
     '{}')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE subscriptions (
    id                      UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID                NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    plan_id                 TEXT                NOT NULL REFERENCES plans (id),
    status                  subscription_status NOT NULL DEFAULT 'trialing',
    razorpay_customer_id    TEXT,
    razorpay_subscription_id TEXT               UNIQUE,
    current_period_start    TIMESTAMPTZ         NOT NULL DEFAULT now(),
    current_period_end      TIMESTAMPTZ         NOT NULL,
    cancel_at_period_end    BOOLEAN             NOT NULL DEFAULT FALSE,
    cancelled_at            TIMESTAMPTZ,
    metadata                JSONB               NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ         NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ         NOT NULL DEFAULT now()
);
CREATE INDEX idx_subscriptions_tenant ON subscriptions (tenant_id);
CREATE INDEX idx_subscriptions_status ON subscriptions (status);
CREATE TRIGGER trg_subscriptions_updated_at BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────
-- USAGE EVENTS (append-only, partitioned by month)
-- ─────────────────────────────────────────
CREATE TABLE usage_events (
    id          BIGSERIAL,
    tenant_id   UUID         NOT NULL,
    meter       meter_kind   NOT NULL,
    quantity    NUMERIC(18,4) NOT NULL CHECK (quantity >= 0),
    occurred_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    idempotency_key TEXT,
    metadata    JSONB        NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

DO $$
DECLARE
    y INT; m INT; s DATE; e DATE;
BEGIN
    FOR y IN 2025..2027 LOOP
        FOR m IN 1..12 LOOP
            s := make_date(y, m, 1);
            e := s + INTERVAL '1 month';
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS usage_events_%s_%s
                 PARTITION OF usage_events
                 FOR VALUES FROM (%L) TO (%L)',
                y, lpad(m::text, 2, '0'), s, e
            );
        END LOOP;
    END LOOP;
END;
$$;

CREATE INDEX idx_usage_tenant_meter_time ON usage_events (tenant_id, meter, occurred_at DESC);
CREATE UNIQUE INDEX idx_usage_idempotency
    ON usage_events (tenant_id, idempotency_key, occurred_at)
    WHERE idempotency_key IS NOT NULL;

-- ─────────────────────────────────────────
-- USAGE ROLLUPS (per-tenant per-meter per-day; rebuilt by background job)
-- ─────────────────────────────────────────
CREATE TABLE usage_rollups_daily (
    tenant_id   UUID         NOT NULL,
    meter       meter_kind   NOT NULL,
    day         DATE         NOT NULL,
    quantity    NUMERIC(18,4) NOT NULL,
    PRIMARY KEY (tenant_id, meter, day)
);
CREATE INDEX idx_usage_rollups_day ON usage_rollups_daily (day);

-- ─────────────────────────────────────────
-- WEBHOOKS (outbound — tenant-controlled)
-- ─────────────────────────────────────────
CREATE TYPE webhook_event_type AS ENUM (
    'forecast.run.started',
    'forecast.run.completed',
    'forecast.run.failed',
    'signal.validated',
    'pharma_batch.released',
    'pharma_batch.recalled',
    'subscription.updated',
    'usage.quota_warning',
    'usage.quota_exceeded'
);

CREATE TABLE webhook_endpoints (
    id                 UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID                NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    url                TEXT                NOT NULL,
    secret             TEXT                NOT NULL,            -- HMAC signing key
    enabled_events     webhook_event_type[] NOT NULL DEFAULT '{}',
    is_active          BOOLEAN             NOT NULL DEFAULT TRUE,
    description        TEXT,
    last_delivery_at   TIMESTAMPTZ,
    failure_count      INTEGER             NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ         NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ         NOT NULL DEFAULT now(),
    CONSTRAINT chk_url_https CHECK (url ~* '^https://')
);
CREATE INDEX idx_webhook_endpoints_tenant ON webhook_endpoints (tenant_id);
CREATE TRIGGER trg_webhook_endpoints_updated_at BEFORE UPDATE ON webhook_endpoints
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE webhook_deliveries (
    id              BIGSERIAL    PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    endpoint_id     UUID         NOT NULL REFERENCES webhook_endpoints (id) ON DELETE CASCADE,
    event_type      webhook_event_type NOT NULL,
    event_id        UUID         NOT NULL DEFAULT gen_random_uuid(),
    payload         JSONB        NOT NULL,
    attempt_count   INTEGER      NOT NULL DEFAULT 0,
    status          TEXT         NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending','succeeded','failed','dead_letter')),
    response_status INTEGER,
    response_body   TEXT,
    next_retry_at   TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_webhook_deliveries_tenant ON webhook_deliveries (tenant_id, created_at DESC);
CREATE INDEX idx_webhook_deliveries_pending ON webhook_deliveries (status, next_retry_at)
    WHERE status = 'pending';

-- ─────────────────────────────────────────
-- RLS
-- ─────────────────────────────────────────
ALTER TABLE subscriptions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events        ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_rollups_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_endpoints   ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries  ENABLE ROW LEVEL SECURITY;

CREATE POLICY subscriptions_isolation       ON subscriptions       USING (bypass_rls() OR tenant_id = current_tenant_id());
CREATE POLICY usage_events_isolation        ON usage_events        USING (bypass_rls() OR tenant_id = current_tenant_id());
CREATE POLICY usage_rollups_isolation       ON usage_rollups_daily USING (bypass_rls() OR tenant_id = current_tenant_id());
CREATE POLICY webhook_endpoints_isolation   ON webhook_endpoints   USING (bypass_rls() OR tenant_id = current_tenant_id());
CREATE POLICY webhook_deliveries_isolation  ON webhook_deliveries  USING (bypass_rls() OR tenant_id = current_tenant_id());

-- Append-only invariants for usage + webhook deliveries
CREATE RULE no_update_usage_events    AS ON UPDATE TO usage_events       DO INSTEAD NOTHING;
CREATE RULE no_delete_usage_events    AS ON DELETE TO usage_events       DO INSTEAD NOTHING;

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON
    subscriptions, webhook_endpoints, webhook_deliveries
TO sanket_app;
GRANT SELECT, INSERT ON usage_events, usage_rollups_daily TO sanket_app;
GRANT SELECT ON plans, regions TO sanket_app;
GRANT USAGE, SELECT ON SEQUENCE webhook_deliveries_id_seq, usage_events_id_seq TO sanket_app;
