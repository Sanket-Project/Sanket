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
