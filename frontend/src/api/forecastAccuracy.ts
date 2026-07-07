import { apiClient } from "@/api/client";

export interface ForecastAccuracyRow {
  sku_id: string;
  model_name: string;
  mape: number | null;
  wape: number | null;
  n_obs: number;
  computed_at: string | null;
}

export interface ForecastAccuracyResponse {
  industry: string;
  source: "cached" | "live";
  rows: ForecastAccuracyRow[];
}

export interface AnomalySkuRow {
  sku_id: string;
  anomaly_count: number;
  latest_anomaly_date: string | null;
  anomaly_rows: { ds: string; y: number; score: number }[];
}

export interface AnomalyResponse {
  industry: string;
  window_days: number;
  sku_count: number;
  anomalous_skus: AnomalySkuRow[];
}

export const forecastAccuracyApi = {
  list: (limit = 100): Promise<ForecastAccuracyResponse> =>
    apiClient.get("/forecast/accuracy", { params: { limit } }).then((r) => r.data),

  anomalies: (days = 90): Promise<AnomalyResponse> =>
    apiClient.get("/anomaly/skus", { params: { days } }).then((r) => r.data),
};
