import { apiClient } from "@/api/client";

/**
 * Revenue is in the currency of the SKUs that sold. When a bucket mixes
 * currencies the API does not add them up: gross/net are null and the
 * per-currency figures are in revenue_by_currency.
 */
export interface SalesBucket {
  units_sold: number;
  gross_revenue: number | null;
  net_revenue: number | null;
  currency: string | null;
  revenue_by_currency: Record<string, number>;
  returns: number;
  transactions: number;
  period_start: string;
  revenue_delta: number | null;
  units_delta: number | null;
}

export interface SalesSummaryResponse {
  industry: string;
  as_of: string;
  today: SalesBucket;
  week: SalesBucket;
  month: SalesBucket;
  year: SalesBucket;
  /** The single currency of all revenue shown, or null when there are several. */
  currency: string | null;
  currencies: string[];
}

export interface SalesTimeseriesPoint {
  bucket: string;
  /** null before the tenant's first recorded sale (no records); 0 is an observed zero. */
  units_sold: number | null;
  gross_revenue: number | null;
  net_revenue: number | null;
  revenue_by_currency?: Record<string, number>;
}

export interface SalesTimeseriesResponse {
  industry: string;
  granularity: "day" | "week" | "month";
  lookback_days: number;
  currency: string | null;
  currencies: string[];
  /** Earliest recorded sale for the tenant + industry, if any. */
  first_sale_at?: string | null;
  /** The bucket containing "now" — still filling up, so incomplete. */
  current_bucket?: string;
  /** Units are gross; returns are not netted. */
  units_basis?: string;
  series: SalesTimeseriesPoint[];
}

export interface TopProductRow {
  sku_id: string;
  sku_code: string;
  product_name: string;
  units_sold: number;
  gross_revenue: number;
  currency: string | null;
  returns: number;
}

export interface TopProductsResponse {
  industry: string;
  period: string;
  products: TopProductRow[];
}

export type TopProductPeriod = "today" | "week" | "month" | "year" | "all";

export interface BranchSalesResponse {
  industry: string;
  period_start: string;
  as_of: string;
  unassigned_records: number;
  branches: { name: string; units_sold: number; gross_revenue: number | null;
    currency: string | null; revenue_by_currency: Record<string, number> }[];
}

export const salesAnalyticsApi = {
  deleteAll: (): Promise<{ deleted: number; industry: string }> =>
    apiClient.delete("/analytics/sales/all").then(r => r.data),
  branches: (lookbackDays = 365, granularity: "day" | "week" | "month" = "month"): Promise<BranchSalesResponse> =>
    apiClient.get("/analytics/sales/branches", { params: { lookback_days: lookbackDays, granularity } }).then(r => r.data),
  summary: (): Promise<SalesSummaryResponse> =>
    apiClient.get("/analytics/sales/summary").then((r) => r.data),

  timeseries: (
    granularity: "day" | "week" | "month" = "day",
    lookbackDays = 30,
  ): Promise<SalesTimeseriesResponse> =>
    apiClient
      .get("/analytics/sales/timeseries", {
        params: { granularity, lookback_days: lookbackDays },
      })
      .then((r) => r.data),

  topProducts: (period: TopProductPeriod = "month", limit = 10): Promise<TopProductsResponse> =>
    apiClient
      .get("/analytics/sales/top-products", { params: { period, limit } })
      .then((r) => r.data),
};
