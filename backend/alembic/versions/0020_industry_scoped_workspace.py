"""Industry-scoped workspaces: one authoritative industry per tenant.

``tenants.active_industry`` becomes ``tenants.industry`` -- the single
authority. The name mattered: "active" implied *currently selected among
several*, which is exactly the model being removed.

``tenants.industries`` and ``users.active_industry`` survive as
database-maintained mirrors rather than being dropped. Two reasons: existing
rows and any not-yet-deployed code keep working through the transition, and a
trigger-maintained mirror cannot drift from its source the way a second
application-written field can. Every previous industry rule lived in Python and
every one of them had a hole -- signup granted all five verticals and the
middleware then trusted the claim signup had filled. This one is enforced where
nothing can route around it.

Non-destructive. Each tenant's prior industry array is snapshotted into
``settings['legacy_industries']`` before being rewritten, and
``industry_profiles`` rows for unselected industries are left in place.

RLS is untouched: no policy is added, altered or dropped. Tenant isolation and
industry scope are different boundaries and this migration only builds the
second one.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants RENAME COLUMN active_industry TO industry")

    # Preserve the prior grant before rewriting it. Nothing is deleted: a tenant
    # that had five verticals can still be seen to have had five verticals.
    op.execute(
        """
        UPDATE tenants
        SET settings = jsonb_set(
            COALESCE(settings, '{}'::jsonb),
            '{legacy_industries}',
            to_jsonb(industries::text[]),
            TRUE
        )
        """
    )
    op.execute("UPDATE tenants SET industries = ARRAY[industry]::industry_code[]")
    op.execute(
        """
        ALTER TABLE tenants
        ADD CONSTRAINT ck_tenants_single_industry
        CHECK (industries = ARRAY[industry]::industry_code[])
        """
    )

    # Every existing member inherits their workspace's industry.
    op.execute(
        """
        UPDATE users u
        SET active_industry = t.industry
        FROM tenants t
        WHERE u.tenant_id = t.id AND u.active_industry IS DISTINCT FROM t.industry
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION tenants_mirror_industries()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public, pg_temp
        AS $$
        BEGIN
            NEW.industries := ARRAY[NEW.industry]::public.industry_code[];
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tenants_mirror_industries
        BEFORE INSERT OR UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION tenants_mirror_industries()
        """
    )

    # SECURITY DEFINER because this reads `tenants`, which RLS hides during a
    # cross-tenant insert -- signup runs without an RLS tenant context, so an
    # invoker-rights function would see no row and silently leave the member's
    # industry unchecked. This is trigger-level privilege created by a
    # migration, not application code opening a superuser connection.
    #
    # The function runs as its owner (a superuser, since migrations connect with
    # MIGRATION_DATABASE_URL), so its search_path must be hostile-proof:
    #   * `pg_temp` is named explicitly and LAST. Omitting it does not exclude
    #     it -- Postgres searches the temp schema FIRST for unqualified
    #     relations -- so any role with the default TEMP privilege could
    #     `CREATE TEMP TABLE tenants(...)` and feed this function whatever it
    #     liked. Naming it last pins it behind the real schemas.
    #   * `tenants` is schema-qualified anyway, belt and braces.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION users_inherit_industry()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, pg_temp
        AS $$
        DECLARE
            tenant_industry public.industry_code;
        BEGIN
            SELECT t.industry INTO tenant_industry
            FROM public.tenants t WHERE t.id = NEW.tenant_id;
            IF tenant_industry IS NOT NULL THEN
                NEW.active_industry := tenant_industry;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_inherit_industry
        BEFORE INSERT OR UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION users_inherit_industry()
        """
    )

    # A dedicated sandbox workspace. The public demo previously signed anonymous
    # visitors into `sanket-dev` -- the shared development tenant, which is also
    # where non-production auto-provisioning puts unknown Google accounts.
    # No `onboarding` key, so the demo never lands in the setup wizard.
    op.execute(
        """
        INSERT INTO tenants (id, slug, display_name, tier, status, industry,
                             max_skus, max_users, data_retention_days, settings)
        VALUES (gen_random_uuid(), 'sandbox', 'SANKET Sandbox', 'growth',
                'active', 'fashion', 1000, 1, 365, '{}'::jsonb)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO users (id, tenant_id, email, password_hash, full_name,
                           role, active_industry, is_active)
        SELECT gen_random_uuid(), id, 'sandbox@sanket.app', NULL,
               'Sandbox Guest', 'viewer', industry, TRUE
        FROM tenants WHERE slug = 'sandbox'
        ON CONFLICT (tenant_id, email) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM users
        WHERE email = 'sandbox@sanket.app'
          AND tenant_id = (SELECT id FROM tenants WHERE slug = 'sandbox')
        """
    )
    op.execute("DELETE FROM tenants WHERE slug = 'sandbox'")
    op.execute("DROP TRIGGER IF EXISTS trg_users_inherit_industry ON users")
    op.execute("DROP FUNCTION IF EXISTS users_inherit_industry()")
    op.execute("DROP TRIGGER IF EXISTS trg_tenants_mirror_industries ON tenants")
    op.execute("DROP FUNCTION IF EXISTS tenants_mirror_industries()")
    op.execute(
        "ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_single_industry"
    )
    op.execute(
        """
        UPDATE tenants
        SET industries = ARRAY(
            SELECT jsonb_array_elements_text(settings -> 'legacy_industries')
        )::industry_code[]
        WHERE settings ? 'legacy_industries'
          AND jsonb_typeof(settings -> 'legacy_industries') = 'array'
        """
    )
    op.execute("UPDATE tenants SET settings = settings - 'legacy_industries'")
    op.execute("ALTER TABLE tenants RENAME COLUMN industry TO active_industry")
