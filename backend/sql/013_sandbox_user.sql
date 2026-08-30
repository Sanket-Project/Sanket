-- SANKET Platform — public sandbox user
--
-- `POST /api/v1/auth/sandbox-session` (the marketing site's "Try the Sandbox"
-- button) looks up a user by `settings.sandbox_email`, which defaults to
-- 'sandbox@sanket-dev.com' in the tenant with slug `settings.sandbox_tenant_slug`
-- ('sanket-dev'). That user was never seeded — 004_seed.sql creates only
-- 'owner@sanket-dev.com' and 'admin@sanket-dev.com'. The lookup therefore
-- returned NULL, raised InvalidCredentialsError, and the landing page's primary
-- CTA responded 401 with "Could not launch sandbox." for every visitor.
--
-- Role is 'viewer' deliberately. The sandbox is a shared, publicly reachable
-- account: anyone on the internet can mint a token for it. An 'admin' there
-- would expose every RBAC-gated mutation, including the billing endpoints
-- (`require_admin_db`), letting anonymous visitors start and cancel
-- subscriptions on the demo tenant.
--
-- No password_hash: sessions for this account are minted server-side by
-- /auth/sandbox-session, never by password login. Leaving it NULL means
-- /auth/dev-login rejects it outright (it requires a non-null hash), so the
-- account cannot be signed into by anyone who guesses the address.
--
-- Idempotent — safe to re-run.
--
-- Apply:
--   docker compose exec postgres psql -U sanket_app -d sanket \
--     -f /docker-entrypoint-initdb.d/013_sandbox_user.sql

DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SET LOCAL app.current_tenant_id = '';

    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'sanket-dev';

    IF v_tenant_id IS NULL THEN
        RAISE NOTICE 'Dev tenant not found — skipping sandbox user seed';
        RETURN;
    END IF;

    INSERT INTO users (
        tenant_id, email, password_hash, full_name, role, active_industry, is_active
    ) VALUES (
        v_tenant_id,
        'sandbox@sanket-dev.com',
        NULL,
        'Sandbox Visitor',
        'viewer',
        'fashion',
        true
    )
    ON CONFLICT (tenant_id, email) DO UPDATE
        SET is_active = true,
            role = 'viewer',
            updated_at = now();

    RAISE NOTICE 'Sandbox user seeded for tenant %', v_tenant_id;
END $$;
