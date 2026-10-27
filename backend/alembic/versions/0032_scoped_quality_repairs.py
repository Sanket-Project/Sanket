"""Narrow junk-row repair under a non-login, FORCE-RLS-bound role."""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sanket_sales_repair') THEN
            CREATE ROLE sanket_sales_repair NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
        IF EXISTS (SELECT FROM pg_roles WHERE rolname='sanket_sales_repair'
                   AND (rolsuper OR rolbypassrls OR rolcanlogin)) THEN
            RAISE EXCEPTION 'Unsafe sales repair role';
        END IF;
    END $$""")
    op.execute("GRANT USAGE ON SCHEMA public TO sanket_sales_repair")
    op.execute("GRANT SELECT, DELETE ON historical_sales TO sanket_sales_repair")
    op.execute("GRANT SELECT, INSERT, UPDATE ON forecast_input_changes TO sanket_sales_repair")
    op.execute("""CREATE FUNCTION sanket_repair_invalid_sales(p_industry industry_code, p_action text)
        RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public SET row_security=on AS $$
        DECLARE v_tenant uuid := public.current_tenant_id(); v_count integer;
        BEGIN
            IF v_tenant IS NULL THEN RAISE EXCEPTION 'Tenant scope is required'; END IF;
            IF p_action='drop_future_sales' THEN
                DELETE FROM public.historical_sales h WHERE h.tenant_id=v_tenant
                    AND h.industry=p_industry AND h.sale_time > clock_timestamp();
            ELSIF p_action='drop_negative_sales' THEN
                DELETE FROM public.historical_sales h WHERE h.tenant_id=v_tenant
                    AND h.industry=p_industry AND h.units_sold < 0;
            ELSE RAISE EXCEPTION 'Unsupported repair action'; END IF;
            GET DIAGNOSTICS v_count=ROW_COUNT;
            RETURN v_count;
        END $$""")
    op.execute("ALTER FUNCTION sanket_repair_invalid_sales(industry_code,text) OWNER TO sanket_sales_repair")
    op.execute("REVOKE ALL ON FUNCTION sanket_repair_invalid_sales(industry_code,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION sanket_repair_invalid_sales(industry_code,text) TO sanket_app")


def downgrade():
    op.execute("DROP FUNCTION sanket_repair_invalid_sales(industry_code,text)")
    op.execute("REVOKE SELECT, DELETE ON historical_sales FROM sanket_sales_repair")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON forecast_input_changes FROM sanket_sales_repair")
