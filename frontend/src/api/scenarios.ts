import { apiClient } from "@/api/client";

/** Scenario levers. Each one changes a physical parameter, never an output. */
export interface ScenarioLevers {
  name?: string;
  preset?: string | null;
  demand_shock_pct: number;
  price_change_pct: number;
  price_elasticity: number;
  lead_time_delta_days: number;
  cost_change_pct: number;
  supplier_outage_weeks: number;
  supplier_outage_sku_ids?: string[];
  service_level?: number | null;
  ramp_weeks: number;
  horizon_weeks: number;
  review_weeks: number;
  sku_ids?: string[];
}

export const DEFAULT_LEVERS: ScenarioLevers = {
  name: "Custom scenario",
  demand_shock_pct: 0,
  price_change_pct: 0,
  price_elasticity: -1.2,
  lead_time_delta_days: 0,
  cost_change_pct: 0,
  supplier_outage_weeks: 0,
  service_level: null,
  ramp_weeks: 0,
  horizon_weeks: 26,
  review_weeks: 4,
};

export interface ScenarioPreset {
  key: string;
  label: string;
  description: string;
  scenario: Partial<ScenarioLevers>;
}

/** Money is null unless every simulated SKU has the unit cost/price it needs. */
export interface PortfolioTotals {
  currency: string;
  skus: number;
  demand_units: number;
  shipped_units: number;
  short_units: number;
  fill_rate: number;
  skus_stocking_out: number;
  revenue: number | null;
  gross_margin: number | null;
  lost_revenue: number | null;
  avg_inventory_units: number;
  peak_inventory_units: number;
  units_ordered: number;
  purchase_spend: number | null;
  holding_cost: number | null;
}

export interface SkuOutcome {
  sku_id: string;
  sku_code: string;
  demand_units: number;
  shipped_units: number;
  short_units: number;
  fill_rate: number;
  weeks_stocked_out: number;
  first_stockout_week: number | null;
  avg_inventory_units: number;
  peak_inventory_units: number;
  ordered_units: number;
  revenue: number | null;
  gross_margin: number | null;
  order_cost: number | null;
  holding_cost: number | null;
}

export interface SkuComparison {
  sku_id: string;
  sku_code: string;
  baseline: SkuOutcome;
  scenario: SkuOutcome;
  delta: {
    fill_rate: number;
    short_units: number;
    revenue: number | null;
    gross_margin: number | null;
    units_ordered: number;
    purchase_spend: number | null;
    avg_inventory_units: number;
  };
  weekly: {
    demand: number[];
    on_hand: number[];
    baseline_on_hand: number[];
  };
}

export interface SimulationResult {
  scenario: Record<string, unknown> & { name: string };
  config: {
    /** Weeks actually simulated — never more than the forecast covers. */
    horizon_weeks: number;
    requested_horizon_weeks?: number;
    forecast_weeks_available?: number;
    /** Set when the request was longer than the forecast and was shortened. */
    horizon_capped_reason?: string | null;
    review_weeks: number;
    holding_cost_pct: number;
    service_level: number;
  };
  baseline: PortfolioTotals;
  result: PortfolioTotals;
  impact: {
    fill_rate_pts: number;
    revenue: number | null;
    gross_margin: number | null;
    lost_revenue: number | null;
    purchase_spend: number | null;
    avg_inventory_units: number;
    skus_stocking_out: number;
  };
  by_sku: SkuComparison[];
  run_id: string;
  skus_simulated: number;
  stock_coverage: { skus_with_recorded_stock: number; skus_total: number };
  valuation_coverage?: { skus_with_cost: number; skus_with_price: number; skus_total: number };
  /** Inputs judged by the same freshness contract as coverage and decisions. */
  readiness?: ScenarioReadiness;
}

export interface ScenarioReadiness {
  forecast_run_id: string;
  forecast_completed_at: string | null;
  forecast_age_days: number | null;
  forecast_stale: boolean;
  skus_missing_stock: string[];
  skus_stale_stock: string[];
  skus_lead_time_assumed: string[];
  skus_missing_cost: string[];
  skus_missing_price: string[];
  assumed_lead_time_days: number;
  /** True when any input is stale, missing or assumed. */
  advisory: boolean;
}

export const scenariosApi = {
  presets: (): Promise<{ presets: ScenarioPreset[] }> =>
    apiClient.get("/scenarios/presets").then((r) => r.data),

  simulate: (levers: ScenarioLevers): Promise<SimulationResult> =>
    apiClient.post("/scenarios/simulate", levers).then((r) => r.data),
};
