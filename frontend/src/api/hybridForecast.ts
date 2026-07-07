import { apiClient } from "./client";
import type {
  HybridForecast,
  HybridForecastRequest,
  HybridRunAccepted,
  HybridRunStatus,
} from "@/types/api";

export const hybridForecastApi = {
  /** Enqueue a hybrid forecast run. Returns immediately with a run_id to poll. */
  create: (body: HybridForecastRequest) =>
    apiClient
      .post<HybridRunAccepted>("/forecast/hybrid/runs", body)
      .then((r) => r.data),

  /** Poll a run; `result` is populated once status === "completed". */
  get: (runId: string) =>
    apiClient
      .get<HybridRunStatus>(`/forecast/hybrid/runs/${runId}`)
      .then((r) => r.data),

  /**
   * Deprecated synchronous variant — blocks ~60s and is subject to client/proxy
   * timeouts. Kept only for backward compatibility; prefer create() + get().
   */
  runSync: (body: HybridForecastRequest) =>
    apiClient
      .post<HybridForecast>("/forecast/hybrid", body, { timeout: 180000 })
      .then((r) => r.data),
};
