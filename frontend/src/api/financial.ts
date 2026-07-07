import { apiClient } from "@/api/client";

export interface FinancialSkuRow {
  sku_id: string;
  sku_code: string;
  unit_price: number;
  unit_cost: number;
  p50_demand: number;
  p90_demand: number;
  safety_stock: number;
  revenue_at_risk: number;
  excess_inventory_cost: number;
  total_impact: number;
}

export interface FinancialImpactResponse {
  industry: string;
  horizon_weeks: number;
  run_id?: string;
  total_revenue_at_risk: number;
  total_excess_cost: number;
  net_impact: number;
  by_sku: FinancialSkuRow[];
}

export interface CostAnalysisRow {
  sku_id: string;
  sku_code: string;
  unit_cost: number;
  unit_price: number;
  on_hand_units: number;
  on_hand_source: "inventory" | "fallback";
  safety_stock: number;
  reorder_point: number;
  holding_cost_annual: number;
  excess_holding_cost: number;
  stockout_exposure_cost: number;
  total_impact: number;
}

export interface CostAnalysisResponse {
  industry: string;
  holding_cost_pct: number;
  totals: { annual_holding_cost: number; stockout_exposure_cost: number; total_impact: number };
  skus: CostAnalysisRow[];
}

export const financialApi = {
  impact: (horizonWeeks = 12): Promise<FinancialImpactResponse> =>
    apiClient.get("/financial/impact", { params: { horizon_weeks: horizonWeeks } }).then((r) => r.data),

  costAnalysis: (holdingCostPct = 0.25): Promise<CostAnalysisResponse> =>
    apiClient.get("/inventory/cost-analysis", { params: { holding_cost_pct: holdingCostPct } }).then((r) => r.data),
};
