import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SalesBucket, SalesSummaryResponse } from "@/api/salesAnalytics";
import { useCurrencyStore } from "@/stores/currency";
import { useAuthStore } from "@/stores/auth";

const api = vi.hoisted(() => ({
  summary: vi.fn(),
  timeseries: vi.fn(),
  topProducts: vi.fn(),
  branches: vi.fn(),
  deleteAll: vi.fn(),
}));
const reports = vi.hoisted(() => vi.fn());
vi.mock("@/api/client", () => ({ apiClient: { get: reports } }));

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
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    api.branches.mockResolvedValue({ branches: [], unassigned_records: 0 });
    reports.mockResolvedValue({ data: { status: "unavailable", report: null } });
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

  it("shows a recoverable report error instead of claiming missing reports are zero sales", async () => {
    api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
    api.topProducts.mockResolvedValue({ products: [] });
    reports.mockRejectedValue(new Error("network failure"));
    renderPage();
    expect(await screen.findByRole("button", { name: "Retry reports" })).toBeInTheDocument();
    expect(screen.queryByText("Today · live feed")).not.toBeInTheDocument();
  });

  it("provides an explicit comparison period and labels deltas against that baseline", async () => {
    api.summary.mockResolvedValue(summary(bucket({ revenue_delta: 0.25, units_delta: -0.1 }), "INR", ["INR"]));
    api.topProducts.mockResolvedValue({ products: [] });
    renderPage();

    expect(await screen.findByLabelText("Sales date range")).toBeInTheDocument();
    expect(screen.getByText(/Comparisons use the same elapsed time/)).toBeInTheDocument();
    expect(screen.getAllByText(/vs the same elapsed period last year/i).length).toBeGreaterThan(0);
  });

  it("honors the full selected history without silently capping daily charts", async () => {
    api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
    api.topProducts.mockResolvedValue({ products: [] });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Your sales, at a glance" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sales performance overview" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Daily" }));
    expect(api.timeseries).toHaveBeenLastCalledWith("day", 365);
    fireEvent.change(screen.getByLabelText("Sales date range"), { target: { value: "90" } });
    expect(await screen.findByText("Last 90 days", { selector: "option" })).toBeInTheDocument();
    expect(api.branches).toHaveBeenLastCalledWith(90, "day");
  });

  it("labels transaction locations as locations, not verified branches", async () => {
    api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
    api.topProducts.mockResolvedValue({ products: [] });
    api.branches.mockResolvedValue({ branches: [{ name: "North", gross_revenue: 1000, units_sold: 10, currency: "INR", revenue_by_currency: { INR: 1000 } }], unassigned_records: 2 });
    renderPage();
    expect(await screen.findByRole("region", { name: "Sales by location" })).toBeInTheDocument();
    expect(screen.getByText(/2 records have no location name/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sales by branch" })).not.toBeInTheDocument();
  });

  it("does not fabricate zero sales when the summary request fails", async () => {
    api.summary.mockRejectedValue(new Error("offline"));
    renderPage();
    expect(await screen.findByRole("button", { name: "Retry sales" })).toBeInTheDocument();
    expect(screen.queryByText("No returns today")).not.toBeInTheDocument();
  });

  it("keeps missing chart history distinct from a recorded zero", async () => {
    api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
    api.topProducts.mockResolvedValue({ products: [] });
    api.timeseries.mockResolvedValue({ currencies: [], currency: null, series: [
      { bucket: "2026-09-01", units_sold: null, gross_revenue: null, net_revenue: null },
    ] });
    renderPage();
    expect(await screen.findByText("No sales history for this date range")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sales by branch" })).not.toBeInTheDocument();
  });

  it("explains change using the last two completed chart periods", async () => {
    api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
    api.topProducts.mockResolvedValue({ products: [] });
    api.timeseries.mockResolvedValue({ currencies: ["INR"], currency: "INR", current_bucket: "2026-10-01", series: [
      { bucket: "2026-08-01", units_sold: 2, gross_revenue: 1000 },
      { bucket: "2026-09-01", units_sold: 3, gross_revenue: 1500 },
      { bucket: "2026-10-01", units_sold: 1, gross_revenue: 100 },
    ] });
    renderPage();
    expect(await screen.findByText(/Sales rose 50.0% in Sep 2026 compared with Aug 2026/)).toBeInTheDocument();
  });
});

it("asks an admin to confirm before deleting sales", async () => {
  act(() => useAuthStore.setState({ role: "admin" }));
  api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
  api.topProducts.mockResolvedValue({ products: [] });
  api.deleteAll.mockResolvedValue({ deleted: 1 });
  api.branches.mockResolvedValue({ branches: [], unassigned_records: 0 });
  api.timeseries.mockResolvedValue({ currency: "INR", currencies: ["INR"], series: [] });
  reports.mockResolvedValue({ data: { status: "unavailable", report: null } });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Delete all sales" }));
  expect(api.deleteAll).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete all sales" }));
  await waitFor(() => expect(api.deleteAll).toHaveBeenCalledOnce());
});

it("shows deletion errors inside the confirmation", async () => {
  act(() => useAuthStore.setState({ role: "admin" }));
  api.summary.mockResolvedValue(summary(bucket({}), "INR", ["INR"]));
  api.topProducts.mockResolvedValue({ products: [] });
  api.branches.mockResolvedValue({ branches: [], unassigned_records: 0 });
  api.timeseries.mockResolvedValue({ currency: "INR", currencies: ["INR"], series: [] });
  api.deleteAll.mockRejectedValue({ response: { data: { detail: "Sales could not be matched." } } });
  reports.mockResolvedValue({ data: { status: "unavailable", report: null } });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Delete all sales" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete all sales" }));
  expect(await within(screen.getByRole("dialog")).findByText("Sales could not be matched.")).toBeInTheDocument();
});
