// Synthetic browser-review responses only. This entry is never imported by src/
// or shipped by the production Vite build. It cannot read or mutate a workspace.
import { AxiosError } from "axios";
import { apiClient } from "../src/api/client";

const codes = ["REVIEW-001", "REVIEW-002", "REVIEW-003", "REVIEW-004", "REVIEW-005"];
const statuses = ["critical", "low", "low", "healthy", "excess"];
const weekly = [1450, 1540, 1380, 1510, 1490, 1530, 1620, 1460, 1760, 1690, 1590, 1740];
const date = (week: number) => new Date(Date.UTC(2026, 7, 3 + week * 7)).toISOString().slice(0, 10);
const forecast = { run_id: "synthetic-review", completed_at: "2026-10-26T08:00:00Z", age_seconds: 7200, horizon_weeks: 12, total_skus: 5, offset: 0, limit: 6, has_more: false, omitted_count: 0, location_status: "ready", rows: Array.from({ length: 12 }, (_, i) => ({ sku_id: "portfolio", forecast_date: date(12 + i), p10: 850 + i * 35, p50: 1640 + i * 12 + (i % 3) * 55, p90: 2780 + i * 46 })) };

export function installPlanningFixture() {
  apiClient.defaults.adapter = async config => {
    const url = config.url ?? "";
    let data: unknown;
    if (url.includes("/decisions")) data = { industry: "fashion", status: "open", count: 0, decisions: [], totals: { purchase_orders: 0, units_to_order: 0, revenue_protected: 0, money_complete: true, critical: 0, currency: "INR" } };
    else if (url.includes("/forecasts/latest")) data = { forecast, refresh: null, stale: false };
    else if (url.includes("/forecasts/confidence")) data = { run_id: "synthetic-review", portfolio_confidence: 35, scored: 5, skus: codes.map((code, i) => ({ sku_id: code, sku_code: code, confidence: [28, 42, 38, 71, 63][i], band: i < 3 ? "low" : "moderate", actionable: false, reasons: ["Synthetic review fixture"], deductions: [] })) };
    else if (url.includes("/analytics/sales/timeseries")) data = { granularity: "week", current_bucket: "2026-10-26", series: weekly.map((units, i) => ({ bucket: date(i), units_sold: units })) };
    else if (url.includes("/inventory/coverage")) data = { industry: "fashion", as_of: "2026-10-26", skus: codes.map((code, i) => ({ sku_id: code, sku_code: code, lead_time_days: 14, lead_time_assumed: false, demand: { basis: "forecast", weekly_units: 50, run_id: "synthetic-review", reason: "Synthetic review fixture" }, sku_wide: { available_units: 20 + i * 50, inbound_units: 0, cover_days: [3, 8, 10, 30, 90][i], status: statuses[i], reason: "Synthetic review fixture" }, locations: [] })) };
    else if (url.includes("/data-quality/report")) data = { critical: 0, warnings: 3, issues_found: 3, health_score: 85, grade: "B", checks_run: 8, findings: [], fixable_automatically: [] };
    else if (url.includes("/integrations/catalog")) data = { connected: 2, total: 2, live: 2, groups: [] };
    else if (url.includes("/notifications/whatsapp")) data = { config: { enabled: false, recipients: [], send_hour: 8, timezone: "Asia/Kolkata" }, delivery: { state: "disabled" } };
    else if (url.includes("/industry/context")) data = { code: "fashion", display_name: "Fashion & Apparel", is_gxp: false };
    else if (url.includes("/billing/subscription")) data = { status: "active" };
    else if (url.includes("/billing/config")) data = { plans: [] };
    else if (url.includes("/alerts")) data = [];
    else throw new AxiosError("Synthetic review: this source is unavailable", "ERR_BAD_RESPONSE", config, undefined, { config, status: 503, statusText: "Unavailable", headers: {}, data: { detail: "Synthetic review source unavailable" } });
    return { config, status: 200, statusText: "OK", headers: {}, data };
  };
}
