-- SANKET Platform — Dev tenant subscription
-- The dev tenant is created with tier='enterprise' and status='active' in
-- 004_seed.sql, but that alone doesn't satisfy SubscriptionGate.tsx, which
-- checks for an actual row in `subscriptions` with status active/trialing
-- and a future current_period_end. Without this, every page except
-- /workspace/billing is blocked by the "Activate Your SANKET Workspace"
-- paywall — which makes it impossible to QA anything else.
--
-- This inserts a real 'active' subscription on the enterprise plan for the
-- dev tenant, dated to run for 10 years, so local/demo testing isn't gated
-- behind the (real-money) Razorpay checkout flow. Idempotent — safe to re-run.
--
-- Apply:
--   docker compose exec postgres psql -U sanket_app -d sanket \
--     -f /docker-entrypoint-initdb.d/011_dev_subscription.sql

DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'sanket-dev';

    IF v_tenant_id IS NULL THEN
        RAISE NOTICE 'Dev tenant not found — skipping subscription seed';
        RETURN;
    END IF;

    PERFORM set_config('app.current_tenant_id', v_tenant_id::text, true);

    IF NOT EXISTS (SELECT 1 FROM subscriptions WHERE tenant_id = v_tenant_id) THEN
        INSERT INTO subscriptions (
            id, tenant_id, plan_id, status,
            current_period_start, current_period_end,
            cancel_at_period_end, metadata
        ) VALUES (
            gen_random_uuid(), v_tenant_id, 'enterprise_monthly', 'active'::subscription_status,
            now(), now() + INTERVAL '10 years',
            false, '{"source": "dev-seed"}'::jsonb
        );
        RAISE NOTICE 'Dev tenant subscription activated (enterprise_monthly) for tenant %', v_tenant_id;
    ELSE
        RAISE NOTICE 'Dev tenant already has a subscription row — leaving as-is';
    END IF;
END;
$$;
