import { apiClient } from "./client";

export type LocationKind = "warehouse" | "store" | "unconfirmed";

export interface Location {
  id: string;
  code: string;
  name: string;
  kind: LocationKind;
  parent_location_id: string | null;
  lead_time_days_from_parent: number | null;
  is_active: boolean;
  last_sale_at?: string | null;
  last_stock_at?: string | null;
}

export interface Network {
  allocation_ready: boolean;
  transfers_ready: boolean;
  missing: string[];
  degraded?: boolean;
  unassigned_share?: number | null;
}

export interface LocationsResponse {
  locations: Location[];
  network: Network;
}

export type LocationPatch = Partial<
  Pick<Location, "name" | "kind" | "parent_location_id" | "lead_time_days_from_parent" | "is_active">
>;

export interface LocationForecast {
  run_id: string | null;
  degraded: boolean;
  unassigned_share: number | null;
  locations: { location_id: string; code: string; name: string; forecast_dates?: string[]; p10: number[]; p50: number[]; p90: number[] }[];
  reason: string | null;
}

export const locationsApi = {
  forecast: (skuId: string, runId?: string) => apiClient.get<LocationForecast>("/locations/forecast", { params: { sku_id: skuId, ...(runId ? { run_id: runId } : {}) } }).then((r) => r.data),
  list: () => apiClient.get<LocationsResponse>("/locations").then((r) => r.data),
  update: (id: string, patch: LocationPatch) =>
    apiClient
      .patch<{ location: Location; network: Network }>(`/locations/${id}`, patch)
      .then((r) => r.data),
};
