import { apiClient } from "@/api/client";

export interface SalesBucket {
  units_sold: number;
  gross_revenue: number;
  net_revenue: number;
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
}

export interface SalesTimeseriesPoint {
  bucket: string;
  units_sold: number;
  gross_revenue: number;
  net_revenue: number;
}

export interface SalesTimeseriesResponse {
  industry: string;
  granularity: "day" | "week" | "month";
  lookback_days: number;
  series: SalesTimeseriesPoint[];
}

export interface TopProductRow {
  sku_id: string;
  sku_code: string;
  product_name: string;
  units_sold: number;
  gross_revenue: number;
  returns: number;
}

export interface TopProductsResponse {
  industry: string;
  period: string;
  products: TopProductRow[];
}

export type TopProductPeriod = "today" | "week" | "month" | "year" | "all";

export const salesAnalyticsApi = {
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
