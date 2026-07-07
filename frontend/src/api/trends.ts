import { apiClient } from "./client";
import type { TrendScore, TrendSignal } from "@/types/api";

export const trendsApi = {
  live: (params?: { kind?: string; hours?: number; limit?: number }) =>
    apiClient
      .get<TrendSignal[]>("/trends/live", { params })
      .then((r) => r.data),

  regional: () =>
    apiClient
      .get<TrendSignal[]>("/trends/regional")
      .then((r) => r.data),

  supplyChain: () =>
    apiClient
      .get<TrendSignal[]>("/trends/supply-chain")
      .then((r) => r.data),

  score: (params?: { horizon_days?: number; lookback_hours?: number }) =>
    apiClient
      .get<TrendScore>("/trends/score", { params })
      .then((r) => r.data),

  economic: (limit = 50) =>
    apiClient
      .get<TrendSignal[]>("/trends/economic", { params: { limit } })
      .then((r) => r.data),

  social: (limit = 50) =>
    apiClient
      .get<TrendSignal[]>("/trends/social", { params: { limit } })
      .then((r) => r.data),

  refresh: () =>
    apiClient
      .post<{ status: string; counts?: Record<string, number> }>("/trends/refresh")
      .then((r) => r.data),
};
