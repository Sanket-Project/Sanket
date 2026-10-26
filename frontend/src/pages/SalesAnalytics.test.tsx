import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SalesBucket, SalesSummaryResponse } from "@/api/salesAnalytics";
import { useCurrencyStore } from "@/stores/currency";

const api = vi.hoisted(() => ({
  summary: vi.fn(),
  timeseries: vi.fn(),
  topProducts: vi.fn(),
}));

vi.mock("@/api/salesAnalytics", () => ({ salesAnalyticsApi: api }));
vi.mock("@/hooks/useWebSocket", () => ({ useWebSocket: () => ({ subscribe: () => () => {} }) }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
vi.mock("@/components/realtime/LiveIndicator", () => ({ LiveIndicator: () => null }));

import { SalesAnalyticsPage } from "@/pages/SalesAnalytics";

const bucket = (over: Partial<SalesBucket>): SalesBucket => ({
  units_sold: 3,
  gross_revenue: 0,
  net_revenue: 0,
  returns: 0,
  transactions: 1,
  period_start: "2026-01-01T00:00:00Z",
  revenue_delta: null,
  units_delta: null,
  currency: "INR",
  revenue_by_currency: {},
  ...over,
});

const summary = (b: SalesBucket, currency: string | null, currencies: string[]): SalesSummaryResponse => ({
  industry: "fashion",
  as_of: "2026-10-26T00:00:00Z",
  today: b,
  week: b,
  month: b,
  year: b,
  currency,
  currencies,
});

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <SalesAnalyticsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("Sales analytics currency (audit F03)", () => {
  beforeEach(() => {
    act(() => useCurrencyStore.setState({ display: "INR", manualRate: null }));
    api.timeseries.mockResolvedValue({ industry: "fashion", granularity: "month", lookback_days: 365,
      currency: "INR", currencies: ["INR"], series: [] });
  });

  it("shows an INR total as the same INR total, not 83x larger", async () => {
    api.summary.mockResolvedValue(
      summary(bucket({ gross_revenue: 13091162, revenue_by_currency: { INR: 13091162 } }), "INR", ["INR"]),
    );
    api.topProducts.mockResolvedValue({ industry: "fashion", period: "year", products: [
      { sku_id: "1", sku_code: "KURTI-M", product_name: "Kurti", units_sold: 3,
        gross_revenue: 500000, currency: "INR", returns: 0 },
    ] });

    renderPage();

    expect((await screen.findAllByText("₹1,30,91,162")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/1,08,65,66,446/)).not.toBeInTheDocument();
    expect(await screen.findByText("₹5,00,000")).toBeInTheDocument();
  });

  it("lists each currency instead of adding rupees to dollars", async () => {
    api.summary.mockResolvedValue(
      summary(bucket({ gross_revenue: null, revenue_by_currency: { INR: 1000, USD: 50 } }), null, ["INR", "USD"]),
    );
    api.topProducts.mockResolvedValue({ industry: "fashion", period: "year", products: [] });

    renderPage();

    expect((await screen.findAllByText(/₹1,000 · \$50/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/mixed currencies/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/1,050/)).not.toBeInTheDocument();
  });
});
