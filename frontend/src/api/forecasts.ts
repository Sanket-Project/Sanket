import { apiClient } from "@/api/client";
import type { ForecastResponse } from "@/types/api";

// Forecast generation goes through the SANKET backend, never directly to the ML
// service. The backend derives tenant_id from the authenticated session, so the
// browser cannot request another tenant's forecast.
export interface ForecastRequestBody {
  horizon?: number;
  force_zero_shot?: boolean;
}

export interface ForecastRefresh {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  industry: string;
  horizon_weeks: number;
  created_at: string;
  completed_at: string | null;
  updated_at?: string;
  base_run_id?: string | null;
  error?: string | null;
}

export interface PersistedForecast extends ForecastResponse {
  completed_at: string;
  age_seconds: number;
  horizon_weeks: number;
  total_skus: number;
  offset: number;
  limit: number;
  has_more: boolean;
  omitted_count: number | null;
  location_status: "ready" | "pending" | "failed";
  location_reason?: string | null;
  sku_labels?: Record<string, { code: string; name: string }>;
}

export interface LatestForecastResponse {
  forecast: PersistedForecast | null;
  refresh: ForecastRefresh | null;
  stale: boolean;
}

export interface LatestForecastParams {
  view?: "summary" | "skus";
  offset?: number;
  limit?: number;
  search?: string;
  run_id?: string;
}

export const forecastsApi = {
  latest: (params: LatestForecastParams = {}) =>
    apiClient.get<LatestForecastResponse>("/forecasts/latest", { params }).then((r) => r.data),
  refresh: (body: ForecastRequestBody & { force?: boolean } = {}) =>
    apiClient.post<Pick<LatestForecastResponse, "refresh" | "stale">>("/forecasts/refresh", body).then((r) => r.data),
  generate: (body: ForecastRequestBody = {}) =>
    apiClient
      .post<ForecastResponse>("/forecasts/generate", body)
      .then((r) => r.data),
  /** Explicit, leakage-free backtest: forecast from history before a past Monday. */
  backtest: (body: { cutoff: string; horizon?: number }) =>
    apiClient.post<ForecastResponse>("/forecasts/backtest", body).then((r) => r.data),
  health: () =>
    apiClient
      .get<{ status: string }>("/forecasts/ml-health")
      .then((r) => r.data),
};

export type ConfidenceBand = "high" | "moderate" | "low" | "insufficient";

export interface SkuConfidence {
  sku_id: string;
  sku_code: string | null;
  confidence: number;
  band: ConfidenceBand;
  actionable: boolean;
  /** Plain-language explanation of every point lost. */
  reasons: string[];
  deductions: Array<{ code: string; points: number; detail: string }>;
}

export interface ConfidenceResponse {
  industry: string;
  run_id: string | null;
  scored: number;
  /** Set when no score could be produced (e.g. no completed forecast run). */
  reason?: string;
  portfolio_confidence?: number;
  score_kind?: "data_readiness";
  score_basis?: string;
  by_band?: Partial<Record<ConfidenceBand, number>>;
  skus: SkuConfidence[];
}

export const forecastConfidenceApi = {
  /** Per-SKU trust score for the latest forecast run, lowest first. */
  list: (limit = 200) =>
    apiClient
      .get<ConfidenceResponse>("/forecasts/confidence", { params: { limit } })
      .then((r) => r.data),
};
