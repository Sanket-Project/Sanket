import { apiClient } from "./client";
import type { TrendScore, TrendSignal } from "@/types/api";

export interface CatalogueTrendOption {
  id: string; label: string; kind: "product" | "sku"; product_id: string;
  product_name: string; sku_code: string | null; category: string;
}
export interface CompanyTrendFilters {
  days?: number; product_id?: string; sku_id?: string; state?: string; district?: string;
}
export interface CompanyTrends {
  catalogue: { product_count: number; sku_count: number };
  period: { days: number; start: string; end: string; previous_start: string };
  sales: {
    status: "available" | "no_history" | "unmapped_geography";
    current_units: number | null; previous_units: number | null; change_pct: number | null;
    observations: number; as_of: string | null;
    series: { date: string; units: number }[];
    leaders: { sku_id: string; sku_code: string; product_name: string; current_units: number; previous_units: number; change_pct: number | null }[];
  };
  external: {
    status: "available" | "no_matches"; as_of: string | null;
    items: { id: string; term: string; source: string; captured_at: string; relative_interest: number | null;
      region: string | null; state: string | null; district: string | null; city: string | null;
      geography_level: "state" | "district" | "city" | "unknown"; matched_products: string[] }[];
  };
}

export const trendsApi = {
  companyRefresh: () => apiClient.post<{ status: "queued" | "running" | "skipped"; reason?: string }>("/trends/company/refresh").then((r) => r.data),
  company: (params: CompanyTrendFilters = {}) => apiClient.get<CompanyTrends>("/trends/company", { params }).then((r) => r.data),
  catalogue: (params: { kind: "product" | "sku"; q?: string; limit?: number; offset?: number; product_id?: string }) =>
    apiClient.get<{ items: CatalogueTrendOption[]; total: number; limit: number; offset: number }>("/trends/company/catalogue", { params }).then((r) => r.data),
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
