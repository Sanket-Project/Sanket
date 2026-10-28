import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { weeklyHistory } from "@/components/dashboard/dashboardData";

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const api = vi.hoisted(() => ({
  decisions: vi.fn(),
  generate: vi.fn(),
  latest: vi.fn(),
  refresh: vi.fn(),
  confidence: vi.fn(),
  quality: vi.fn(),
  catalog: vi.fn(),
  timeseries: vi.fn(),
  coverage: vi.fn(),
}));
vi.mock("@/api/decisions", () => ({ decisionsApi: { list: api.decisions, accept: vi.fn() } }));
vi.mock("@/api/forecasts", () => ({
  forecastsApi: { generate: api.generate, latest: api.latest, refresh: api.refresh },
  forecastConfidenceApi: { list: api.confidence },
}));
vi.mock("@/api/dataQuality", () => ({ dataQualityApi: { report: api.quality } }));
vi.mock("@/api/integrations", () => ({ integrationsApi: { catalog: api.catalog } }));
vi.mock("@/api/salesAnalytics", () => ({ salesAnalyticsApi: { timeseries: api.timeseries } }));
vi.mock("@/api/inventory", () => ({ inventoryApi: { coverage: api.coverage } }));
vi.mock("@/components/dashboard/WhatsAppStatus", () => ({ WhatsAppStatus: () => null }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { PlanningBriefDashboard } from "@/components/dashboard/PlanningBriefDashboard";

const sku = (id: string, band: string, lead_time_assumed = false) => ({ sku_id: id, sku_code: id, band, lead_time_assumed });

function happyPath() {
  api.decisions.mockResolvedValue({
    industry: "fashion", status: "open", count: 0, decisions: [],
    totals: { purchase_orders: 0, units_to_order: 0, capital_committed: 0,
      working_capital_released_vs_baseline: 0, revenue_protected: 0, money_complete: true,
      critical: 0, currency: "INR" },
  });
  api.latest.mockResolvedValue({ stale: false, refresh: null, forecast: { run_id: "saved", completed_at: "2026-10-26T00:00:00Z", age_seconds: 7200, horizon_weeks: 12, rows: [
    { sku_id: "a", forecast_date: "2026-10-26", p10: 8, p50: 10, p90: 12 },
    { sku_id: "b", forecast_date: "2026-10-26", p10: 4, p50: 5, p90: 6 },
  ] } });
  api.refresh.mockResolvedValue({ stale: true, refresh: { id: "job", status: "pending" } });
  api.confidence.mockResolvedValue({
    industry: "fashion", run_id: "r", scored: 6, portfolio_confidence: 78,
    skus: [sku("a", "high"), sku("b", "high"), sku("c", "low"), sku("d", "low"),
      sku("e", "insufficient"), sku("f", "low")],
  });
  api.quality.mockResolvedValue({ issues_found: 2, critical: 1, warnings: 1, findings: [] });
  api.catalog.mockResolvedValue({ connected: 1, total: 42, live: 6, groups: [] });
  api.timeseries.mockResolvedValue({
    granularity: "week", current_bucket: "2026-10-26",
    series: [
      { bucket: "2026-10-12", units_sold: 12 },
      { bucket: "2026-10-19", units_sold: 0 },
      { bucket: "2026-10-26", units_sold: 2 },
    ],
  });
  api.coverage.mockResolvedValue({ skus: [
    { sku_id: "a", lead_time_assumed: true }, { sku_id: "b", lead_time_assumed: true },
    { sku_id: "c", lead_time_assumed: false },
  ] });
}

const renderDashboard = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><PlanningBriefDashboard /></MemoryRouter>
    </QueryClientProvider>,
  );

describe("weeklyHistory (deep audit F4, F5)", () => {
  it("keeps complete weeks, including zero weeks, and drops the partial current week", () => {
    expect(weeklyHistory({
      current_bucket: "2026-10-26",
      series: [
        { bucket: "2026-10-05", units_sold: null },
        { bucket: "2026-10-12", units_sold: 12 },
        { bucket: "2026-10-19", units_sold: 0 },
        { bucket: "2026-10-26", units_sold: 2 },
      ],
    })).toEqual([
      { date: "2026-10-05", actual: null },
      { date: "2026-10-12", actual: 12 },
      { date: "2026-10-19", actual: 0 },
    ]);
  });
});

describe("PlanningBriefDashboard", () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    happyPath();
  });

  it("marks the dashboard's saved forecast as stale while new data is being processed", async () => {
    const saved = await api.latest();
    api.latest.mockResolvedValue({ ...saved, stale: true,
      refresh: { id: "refresh", status: "running", industry: "fashion" } });
    renderDashboard();
    expect(await screen.findByText(/Saved forecast is out of date/)).toBeInTheDocument();
  });

  it("charts weekly actuals against the weekly forecast, labelled per week", async () => {
    renderDashboard();

    await screen.findByText("units / week");
    expect(api.timeseries).toHaveBeenCalledWith("week", 84);
  });

  it("does not call summed per-SKU bounds a calibrated portfolio range", async () => {
    renderDashboard();

    expect(await screen.findByText(/sum of per-SKU P10–P90 ranges/i)).toBeInTheDocument();
    expect(screen.queryByText(/the light band shows the plausible range/i)).not.toBeInTheDocument();
  });

  it("shows what the confidence and warning figures are made of", async () => {
    renderDashboard();

    const lowConfidence = await screen.findByRole("link", { name: /4 low-confidence SKUs/i });
    expect(lowConfidence).toHaveAttribute("href", "/workspace/forecasts");
    expect(screen.getByRole("link", { name: /1 critical data issue/i })).toHaveAttribute("href", "/workspace/data-quality");
    expect(screen.getByText(/2 SKUs use an assumed lead time/i)).toBeInTheDocument();
    expect(screen.getByText(/not a held-out accuracy score/i)).toBeInTheDocument();
  });

  it("places confidence once in a labelled summary with its band and reasons", async () => {
    renderDashboard();

    const field = await screen.findByRole("group", { name: "Forecast confidence" });
    expect(await within(field).findByText("78 / 100")).toBeInTheDocument();
    expect(within(field).getByText("Moderate")).toBeInTheDocument();
    expect(within(field).getByRole("link", { name: "View reasons" })).toHaveAttribute("href", "/workspace/forecasts");
    expect(screen.queryByText("78% confidence")).not.toBeInTheDocument();
    expect(screen.getAllByText("Forecast confidence")).toHaveLength(1);
  });

  it("keeps a zero confidence score visible instead of hiding it", async () => {
    api.confidence.mockResolvedValue({ industry: "fashion", scored: 1, portfolio_confidence: 0, skus: [] });
    renderDashboard();
    const field = await screen.findByRole("group", { name: "Forecast confidence" });
    expect(await within(field).findByText("0 / 100")).toBeInTheDocument();
    expect(within(field).getByText("Low")).toBeInTheDocument();
  });

  it("explains missing confidence without showing a made-up score or band", async () => {
    api.confidence.mockResolvedValue({ industry: "fashion", run_id: null, scored: 0, reason: "No completed forecast run", skus: [] });
    renderDashboard();
    const field = await screen.findByRole("group", { name: "Forecast confidence" });
    expect(await within(field).findByText("Not scored")).toBeInTheDocument();
    expect(within(field).getByText("No completed forecast run")).toBeInTheDocument();
    expect(within(field).queryByText("Low")).not.toBeInTheDocument();
  });

  it("keeps the empty planning card concise without a sample product image", async () => {
    renderDashboard();
    expect(await screen.findByRole("heading", { name: "Review demand and stock" })).toBeInTheDocument();
    expect(screen.queryByAltText("fashion catalogue product")).not.toBeInTheDocument();
  });

  it("says decisions are unavailable when they fail to load, not that none are open", async () => {
    api.decisions.mockRejectedValue(new Error("503"));

    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent(/decisions could not be loaded/i);
    expect(screen.getByText("Orders due").parentElement).toHaveTextContent("Unavailable");
    expect(screen.queryByText("No open order decision currently requires approval.")).not.toBeInTheDocument();
  });

  it("shows unavailable rather than zero when the data-quality check fails", async () => {
    api.quality.mockRejectedValue(new Error("503"));

    renderDashboard();

    await screen.findByText("Data warnings");
    await waitFor(() => expect(screen.getByTestId("summary-data-warnings")).toHaveTextContent("Unavailable"));
  });

  it("refreshes every dependent panel together", async () => {
    renderDashboard();
    await screen.findByText(/4 low-confidence SKUs/i);
    const before = { quality: api.quality.mock.calls.length, coverage: api.coverage.mock.calls.length,
      confidence: api.confidence.mock.calls.length, catalog: api.catalog.mock.calls.length };

    fireEvent.click(screen.getByRole("button", { name: /refresh brief/i }));

    await waitFor(() => {
      expect(api.quality.mock.calls.length).toBeGreaterThan(before.quality);
      expect(api.coverage.mock.calls.length).toBeGreaterThan(before.coverage);
      expect(api.confidence.mock.calls.length).toBeGreaterThan(before.confidence);
      expect(api.catalog.mock.calls.length).toBeGreaterThan(before.catalog);
    });
  });

  it("keeps the saved forecast visible and reports when a later read fails", async () => {
    renderDashboard();
    await screen.findByText(/Generated 2 hours ago/);
    api.latest.mockRejectedValue(new Error("Saved forecast read failed"));
    fireEvent.click(screen.getByRole("button", { name: /refresh brief/i }));
    expect(await screen.findByText(/Saved forecast read failed/)).toBeInTheDocument();
    expect(screen.getByText(/Generated 2 hours ago/)).toBeInTheDocument();
  });
});

it("loads the persisted portfolio summary and age without generating on every visit", async () => {
  Object.values(api).forEach((fn) => fn.mockReset());
  happyPath();
  renderDashboard();
  expect(await screen.findByText(/Generated 2 hours ago/)).toBeInTheDocument();
  expect(api.latest).toHaveBeenCalledWith({ view: "summary", offset: 0, limit: 6 });
  expect(api.generate).not.toHaveBeenCalled();
});

it("offers an optional grounded summary above the existing planning metrics", async () => {
  happyPath();
  renderDashboard();
  expect(await screen.findByRole("complementary", { name: "AI summary" })).toBeInTheDocument();
  expect(screen.getByText("Orders due")).toBeInTheDocument();
});

it("retains a generated summary when unchanged source data is polled again", async () => {
  const { aiApi } = await import("@/api/ai");
  const summary = vi.spyOn(aiApi, "summary").mockResolvedValue({ state: "success", blocks: [{ text: "Stable summary", kind: "fact", sources: [] }] });
  happyPath();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><PlanningBriefDashboard /></MemoryRouter></QueryClientProvider>);
  await screen.findByText(/4 low-confidence SKUs/i);
  fireEvent.click(screen.getByRole("button", { name: "Generate AI summary" }));
  await screen.findByText("Stable summary");
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["data-quality"] });
    // React Query batches observer notifications on the next timer turn.
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  expect(screen.getByText("Stable summary")).toBeInTheDocument();
  summary.mockRestore();
});
