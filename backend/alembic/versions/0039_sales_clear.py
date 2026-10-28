"""Allow tenant-scoped sales clearing without granting the app DELETE on history."""
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION sanket_clear_sales(p_industry industry_code)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public SET row_security=on AS $$
        DECLARE v_tenant uuid := public.current_tenant_id(); v_count integer;
        BEGIN
            IF v_tenant IS NULL THEN RAISE EXCEPTION 'Tenant scope is required'; END IF;
            DELETE FROM public.historical_sales h
                WHERE h.tenant_id=v_tenant AND h.industry=p_industry;
            GET DIAGNOSTICS v_count=ROW_COUNT;
            RETURN v_count;
        END $$""")
    op.execute("ALTER FUNCTION sanket_clear_sales(industry_code) OWNER TO sanket_sales_repair")
    op.execute("REVOKE ALL ON FUNCTION sanket_clear_sales(industry_code) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION sanket_clear_sales(industry_code) TO sanket_app")


def downgrade():
    op.execute("DROP FUNCTION sanket_clear_sales(industry_code)")
