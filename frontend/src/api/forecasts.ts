import { apiClient } from "@/api/client";
import type { ForecastResponse } from "@/types/api";

// Forecast generation goes through the SANKET backend, never directly to the ML
// service. The backend derives tenant_id from the authenticated session, so the
// browser cannot request another tenant's forecast.
export interface ForecastRequestBody {
  horizon?: number;
  force_zero_shot?: boolean;
}

export const forecastsApi = {
  generate: (body: ForecastRequestBody = {}) =>
    apiClient
      .post<ForecastResponse>("/forecasts/generate", body)
      .then((r) => r.data),
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
