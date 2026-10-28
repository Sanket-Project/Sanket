import { apiClient } from "@/api/client";

export interface ProjectionLocation {
  location: string;
  available_units: number;
  weekly_units: number | null;
  projected_units: number | null;
  estimated_cover_days: number | null;
  reason: string;
}
export interface ProjectionRow {
  sku_id: string;
  sku_code: string;
  product_name: string;
  reported_units: number;
  days: number;
  weekly_units: number;
  projected_units: number;
  available_units: number;
  estimated_cover_days: number | null;
  locations: ProjectionLocation[];
}
export interface PeriodProjection {
  status: "available" | "unavailable";
  basis: "period_average";
  as_of: string;
  catalogue_skus: number;
  matched_skus: number;
  eligible_skus: number;
  missing_skus: number;
  unsupported_skus: number;
  filtered_skus: number;
  offset: number;
  limit: number;
  projected_units: number;
  projection_start: string;
  projection_end: string;
  horizon_weeks: number;
  source_periods: { start: string; end: string; days: number; source: string }[];
  limitations: string[];
  rows: ProjectionRow[];
}
export const periodProjectionApi = {
  get: (params: { horizon_weeks?: number; offset?: number; limit?: number; search?: string } = {}) =>
    apiClient.get<PeriodProjection>("/forecasts/average-sales", { params }).then(r => r.data),
};
