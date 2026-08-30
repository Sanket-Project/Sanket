import { apiClient } from "@/api/client";

export type DecisionKind = "purchase_order" | "excess_stock" | "safety_stock_update";
export type DecisionStatus = "open" | "accepted" | "dismissed" | "expired";
export type DecisionUrgency = "critical" | "high" | "normal" | "low";
export type ConfidenceBand = "high" | "moderate" | "low" | "insufficient";

export interface DecisionReason {
  code: string;
  text: string;
  impact_units: number | null;
}

/** Every number the recommendation was derived from — the UI shows the working. */
export interface DecisionInputs {
  lead_time_days: number;
  review_period_days: number;
  protection_days: number;
  service_level: number;
  z: number;
  demand_p50_over_window: number;
  demand_p90_over_window: number;
  sigma_over_window: number;
  safety_stock_units: number;
  order_up_to: number;
  on_hand_units: number;
  reserved_units: number;
  inbound_units: number;
  position_units: number;
  days_of_cover: number | null;
  moq: number;
  unit_cost: number;
  unit_price: number;
  forecast_horizon_weeks: number;
  holding_cost_pct: number;
}

export interface DecisionEconomics {
  currency: string;
  capital_committed?: number;
  baseline_capital?: number;
  working_capital_released?: number;
  holding_cost_over_window?: number;
  revenue_protected?: number;
  units_at_risk_without_order?: number;
  excess_units?: number;
  capital_locked?: number;
  annual_holding_cost?: number;
  capital_delta?: number;
  note?: string;
}

export interface Decision {
  id: string;
  sku_id: string;
  sku_code: string | null;
  kind: DecisionKind;
  status: DecisionStatus;
  urgency: DecisionUrgency;
  headline: string;
  recommended_units: number;
  baseline_units: number;
  accepted_units: number | null;
  confidence: number;
  confidence_band: ConfidenceBand;
  currency: string;
  unit_cost: number;
  unit_price: number;
  reasons: DecisionReason[];
  economics: DecisionEconomics;
  inputs: DecisionInputs;
  linked_alert_id: string | null;
  created_at: string | null;
  decided_at: string | null;
  expires_at: string | null;
}

export interface DecisionTotals {
  purchase_orders: number;
  units_to_order: number;
  capital_committed: number;
  working_capital_released_vs_baseline: number;
  revenue_protected: number;
  critical: number;
  currency: string;
}

export interface DecisionListResponse {
  industry: string;
  status: string;
  count: number;
  decisions: Decision[];
  totals: DecisionTotals;
}

export interface RefreshResponse {
  industry: string;
  generated: number;
  skus_evaluated: number;
  run_id?: string | null;
  /** Present when nothing could be produced — explains why, e.g. no forecast run. */
  reason?: string;
  decisions: Decision[];
  totals: DecisionTotals;
}

export interface DecisionPolicy {
  service_level: number;
  review_period_days: number;
  holding_cost_pct: number;
  min_confidence_to_act: number;
}

export const decisionsApi = {
  list: (params?: { status?: string; kind?: DecisionKind; limit?: number }): Promise<DecisionListResponse> =>
    apiClient.get("/decisions", { params }).then((r) => r.data),

  refresh: (): Promise<RefreshResponse> =>
    apiClient.post("/decisions/refresh").then((r) => r.data),

  accept: (id: string, body?: { units?: number; note?: string }): Promise<Decision> =>
    apiClient.post(`/decisions/${id}/accept`, body ?? {}).then((r) => r.data),

  dismiss: (id: string, reason?: string): Promise<Decision> =>
    apiClient.post(`/decisions/${id}/dismiss`, { reason }).then((r) => r.data),

  getPolicy: (): Promise<DecisionPolicy> =>
    apiClient.get("/decisions/policy").then((r) => r.data),

  updatePolicy: (body: DecisionPolicy): Promise<DecisionPolicy> =>
    apiClient.put("/decisions/policy", body).then((r) => r.data),
};
