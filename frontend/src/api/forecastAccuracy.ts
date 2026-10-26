import { apiClient } from "@/api/client";

export interface AccuracyWeek {
  week: string;
  actual: number;
  p10: number;
  p50: number;
  p90: number;
  run_id: string;
  lead_weeks: number;
}

export interface ForecastAccuracyRow {
  sku_id: string;
  sku_code: string | null;
  model_name: string;
  mape: number | null;
  /** Null when nothing sold in the scored weeks (undefined, not 0%). */
  wape: number | null;
  bias_pct: number | null;
  coverage_p10_p90: number | null;
  n_obs: number;
  computed_at: string | null;
  weeks: AccuracyWeek[];
}

export interface BacktestRun {
  run_id: string;
  cutoff: string | null;
  completed_at: string;
  points: number;
  skus: number;
  wape: number | null;
  bias_pct: number | null;
  mape: number | null;
  coverage_p10_p90: number | null;
}

export interface ForecastAccuracyResponse {
  industry: string;
  source: "live";
  calendar: string;
  basis: string;
  /** Production accuracy: forecasts made before each week began. */
  rows: ForecastAccuracyRow[];
  summary: { points: number; skus: number; wape: number | null; bias_pct: number | null; coverage_p10_p90: number | null };
  /** Forecasts not scored, by reason. */
  excluded: Record<string, number>;
  /** Explicit after-the-fact backtests, never mixed into production accuracy. */
  backtest: { note: string; runs: BacktestRun[] };
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
