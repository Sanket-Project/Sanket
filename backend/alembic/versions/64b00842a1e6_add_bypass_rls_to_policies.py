"""add_bypass_rls_to_policies

Revision ID: 64b00842a1e6
Revises: 0012
Create Date: 2026-06-13 23:50:22.832460

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '64b00842a1e6'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Define bypass_rls helper function
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bypass_rls() RETURNS BOOLEAN
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
            SELECT COALESCE(current_setting('app.bypass_rls', TRUE) = 'true', FALSE);
        $$;
        """
    )

    # 2. Re-create policies with RLS bypass support
    op.execute("DROP POLICY IF EXISTS tenants_isolation ON tenants")
    op.execute("CREATE POLICY tenants_isolation ON tenants USING (bypass_rls() OR id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS users_isolation ON users")
    op.execute("CREATE POLICY users_isolation ON users USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS industry_profiles_isolation ON industry_profiles")
    op.execute("CREATE POLICY industry_profiles_isolation ON industry_profiles USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS products_isolation ON products")
    op.execute("CREATE POLICY products_isolation ON products USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS skus_isolation ON skus")
    op.execute("CREATE POLICY skus_isolation ON skus USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS historical_sales_isolation ON historical_sales")
    op.execute("CREATE POLICY historical_sales_isolation ON historical_sales USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS pharma_batches_isolation ON pharma_batches")
    op.execute("CREATE POLICY pharma_batches_isolation ON pharma_batches USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS external_signals_isolation ON external_signals")
    op.execute("CREATE POLICY external_signals_isolation ON external_signals USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS signal_clusters_isolation ON signal_clusters")
    op.execute("CREATE POLICY signal_clusters_isolation ON signal_clusters USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS forecast_runs_isolation ON forecast_runs")
    op.execute("CREATE POLICY forecast_runs_isolation ON forecast_runs USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS forecast_results_isolation ON forecast_results")
    op.execute("CREATE POLICY forecast_results_isolation ON forecast_results USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS audit_log_isolation ON audit_log")
    op.execute("CREATE POLICY audit_log_isolation ON audit_log USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS refresh_tokens_isolation ON refresh_tokens")
    op.execute("CREATE POLICY refresh_tokens_isolation ON refresh_tokens USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS pos_ingest_isolation ON pos_ingest")
    op.execute("CREATE POLICY pos_ingest_isolation ON pos_ingest USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS forecast_accuracy_metrics_isolation ON forecast_accuracy_metrics")
    op.execute("CREATE POLICY forecast_accuracy_metrics_isolation ON forecast_accuracy_metrics USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS supplier_lead_time_log_isolation ON supplier_lead_time_log")
    op.execute("CREATE POLICY supplier_lead_time_log_isolation ON supplier_lead_time_log USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS data_quality_issues_isolation ON data_quality_issues")
    op.execute("CREATE POLICY data_quality_issues_isolation ON data_quality_issues USING (bypass_rls() OR tenant_id IS NULL OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS subscriptions_isolation ON subscriptions")
    op.execute("CREATE POLICY subscriptions_isolation ON subscriptions USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS usage_events_isolation ON usage_events")
    op.execute("CREATE POLICY usage_events_isolation ON usage_events USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS usage_rollups_isolation ON usage_rollups_daily")
    op.execute("CREATE POLICY usage_rollups_isolation ON usage_rollups_daily USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS webhook_endpoints_isolation ON webhook_endpoints")
    op.execute("CREATE POLICY webhook_endpoints_isolation ON webhook_endpoints USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS webhook_deliveries_isolation ON webhook_deliveries")
    op.execute("CREATE POLICY webhook_deliveries_isolation ON webhook_deliveries USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS trend_signals_select ON trend_signals")
    op.execute("DROP POLICY IF EXISTS trend_signals_modify ON trend_signals")
    op.execute(
        """
        CREATE POLICY trend_signals_select ON trend_signals
            FOR SELECT TO sanket_app
            USING (bypass_rls() OR tenant_id IS NULL OR tenant_id = current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY trend_signals_modify ON trend_signals
            FOR ALL TO sanket_app
            USING (bypass_rls() OR tenant_id IS NULL OR tenant_id = current_tenant_id())
            WITH CHECK (bypass_rls() OR tenant_id IS NULL OR tenant_id = current_tenant_id());
        """
    )

    op.execute("DROP POLICY IF EXISTS hybrid_runs_tenant ON hybrid_forecast_runs")
    op.execute(
        """
        CREATE POLICY hybrid_runs_tenant ON hybrid_forecast_runs
            FOR ALL TO sanket_app
            USING (bypass_rls() OR tenant_id = current_tenant_id())
            WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());
        """
    )

    op.execute("DROP POLICY IF EXISTS alert_rules_tenant ON alert_rules")
    op.execute(
        """
        CREATE POLICY alert_rules_tenant ON alert_rules
            FOR ALL TO sanket_app
            USING (bypass_rls() OR tenant_id = current_tenant_id())
            WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());
        """
    )

    op.execute("DROP POLICY IF EXISTS shortage_alerts_tenant ON shortage_alerts")
    op.execute(
        """
        CREATE POLICY shortage_alerts_tenant ON shortage_alerts
            FOR ALL TO sanket_app
            USING (bypass_rls() OR tenant_id = current_tenant_id())
            WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());
        """
    )

    op.execute("DROP POLICY IF EXISTS inventory_levels_isolation ON inventory_levels")
    op.execute("CREATE POLICY inventory_levels_isolation ON inventory_levels USING (bypass_rls() OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS integration_connections_isolation ON integration_connections")
    op.execute("CREATE POLICY integration_connections_isolation ON integration_connections USING (bypass_rls() OR tenant_id = current_tenant_id())")


def downgrade() -> None:
    # Re-create original policies without RLS bypass support
    op.execute("DROP POLICY IF EXISTS tenants_isolation ON tenants")
    op.execute("CREATE POLICY tenants_isolation ON tenants USING (id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS users_isolation ON users")
    op.execute("CREATE POLICY users_isolation ON users USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS industry_profiles_isolation ON industry_profiles")
    op.execute("CREATE POLICY industry_profiles_isolation ON industry_profiles USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS products_isolation ON products")
    op.execute("CREATE POLICY products_isolation ON products USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS skus_isolation ON skus")
    op.execute("CREATE POLICY skus_isolation ON skus USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS historical_sales_isolation ON historical_sales")
    op.execute("CREATE POLICY historical_sales_isolation ON historical_sales USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS pharma_batches_isolation ON pharma_batches")
    op.execute("CREATE POLICY pharma_batches_isolation ON pharma_batches USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS external_signals_isolation ON external_signals")
    op.execute("CREATE POLICY external_signals_isolation ON external_signals USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS signal_clusters_isolation ON signal_clusters")
    op.execute("CREATE POLICY signal_clusters_isolation ON signal_clusters USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS forecast_runs_isolation ON forecast_runs")
    op.execute("CREATE POLICY forecast_runs_isolation ON forecast_runs USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS forecast_results_isolation ON forecast_results")
    op.execute("CREATE POLICY forecast_results_isolation ON forecast_results USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS audit_log_isolation ON audit_log")
    op.execute("CREATE POLICY audit_log_isolation ON audit_log USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS refresh_tokens_isolation ON refresh_tokens")
    op.execute("CREATE POLICY refresh_tokens_isolation ON refresh_tokens USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS pos_ingest_isolation ON pos_ingest")
    op.execute("CREATE POLICY pos_ingest_isolation ON pos_ingest USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS forecast_accuracy_metrics_isolation ON forecast_accuracy_metrics")
    op.execute("CREATE POLICY forecast_accuracy_metrics_isolation ON forecast_accuracy_metrics USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS supplier_lead_time_log_isolation ON supplier_lead_time_log")
    op.execute("CREATE POLICY supplier_lead_time_log_isolation ON supplier_lead_time_log USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS data_quality_issues_isolation ON data_quality_issues")
    op.execute("CREATE POLICY data_quality_issues_isolation ON data_quality_issues USING (tenant_id IS NULL OR tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS subscriptions_isolation ON subscriptions")
    op.execute("CREATE POLICY subscriptions_isolation ON subscriptions USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS usage_events_isolation ON usage_events")
    op.execute("CREATE POLICY usage_events_isolation ON usage_events USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS usage_rollups_isolation ON usage_rollups_daily")
    op.execute("CREATE POLICY usage_rollups_isolation ON usage_rollups_daily USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS webhook_endpoints_isolation ON webhook_endpoints")
    op.execute("CREATE POLICY webhook_endpoints_isolation ON webhook_endpoints USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS webhook_deliveries_isolation ON webhook_deliveries")
    op.execute("CREATE POLICY webhook_deliveries_isolation ON webhook_deliveries USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS trend_signals_select ON trend_signals")
    op.execute("DROP POLICY IF EXISTS trend_signals_modify ON trend_signals")
    op.execute(
        """
        CREATE POLICY trend_signals_select ON trend_signals
            FOR SELECT TO sanket_app
            USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY trend_signals_modify ON trend_signals
            FOR ALL TO sanket_app
            USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )

    op.execute("DROP POLICY IF EXISTS hybrid_runs_tenant ON hybrid_forecast_runs")
    op.execute(
        """
        CREATE POLICY hybrid_runs_tenant ON hybrid_forecast_runs
            FOR ALL TO sanket_app
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )

    op.execute("DROP POLICY IF EXISTS alert_rules_tenant ON alert_rules")
    op.execute(
        """
        CREATE POLICY alert_rules_tenant ON alert_rules
            FOR ALL TO sanket_app
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )

    op.execute("DROP POLICY IF EXISTS shortage_alerts_tenant ON shortage_alerts")
    op.execute(
        """
        CREATE POLICY shortage_alerts_tenant ON shortage_alerts
            FOR ALL TO sanket_app
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )

    op.execute("DROP POLICY IF EXISTS inventory_levels_isolation ON inventory_levels")
    op.execute("CREATE POLICY inventory_levels_isolation ON inventory_levels USING (tenant_id = current_tenant_id())")

    op.execute("DROP POLICY IF EXISTS integration_connections_isolation ON integration_connections")
    op.execute("CREATE POLICY integration_connections_isolation ON integration_connections USING (tenant_id = current_tenant_id())")

    # Drop bypass_rls helper function
    op.execute("DROP FUNCTION IF EXISTS bypass_rls()")
