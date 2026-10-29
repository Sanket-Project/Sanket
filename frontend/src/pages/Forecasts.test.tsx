import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PersistedForecast } from "@/api/forecasts";
import type { ForecastResponse } from "@/types/api";

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one to mount.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const api = vi.hoisted(() => ({
  generate: vi.fn(),
  latest: vi.fn(),
  refresh: vi.fn(),
  decisions: vi.fn(),
  skus: vi.fn(),
  locationForecast: vi.fn(),
  average: vi.fn(),
}));
vi.mock("@/api/periodProjection", () => ({ periodProjectionApi: { get: api.average } }));
beforeEach(() => { api.average.mockResolvedValue({ status: "unavailable" }); });

vi.mock("@/api/forecasts", () => ({
  forecastsApi: { generate: api.generate, latest: api.latest, refresh: api.refresh },
  forecastConfidenceApi: { list: vi.fn().mockResolvedValue({ industry: "fashion", run_id: null, scored: 0, skus: [] }) },
}));
vi.mock("@/api/decisions", () => ({ decisionsApi: { list: api.decisions } }));
vi.mock("@/api/skus", () => ({ skusApi: { list: api.skus } }));
vi.mock("@/api/locations", () => ({ locationsApi: { forecast: api.locationForecast } }));
vi.mock("@/api/export", () => ({ exportApi: { forecastXlsx: vi.fn(), signalsCsv: vi.fn() } }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { ForecastsPage } from "@/pages/Forecasts";

const response = (n: number, extra: Partial<PersistedForecast> = {}): PersistedForecast => ({
  run_id: "run-1",
  n_predictions: n * 2,
  source: "chronos_zero_shot",
  context_source: "database",
  n_series: n,
  calendar: "W-MON-UTC",
  history_end: "2026-10-26",
  first_forecast_week: "2026-10-26",
  omitted: [],
  completed_at: "2026-10-26T00:00:00Z", age_seconds: 7200, horizon_weeks: 12,
  total_skus: n, offset: 0, limit: 6, has_more: n > 6, omitted_count: extra.omitted?.length ?? 0,
  location_status: "ready",
  sku_labels: Object.fromEntries(skuList(8).map((sku) => [sku.id, { code: sku.sku_code, name: sku.description }])),
  rows: Array.from({ length: n }, (_, i) =>
    ["2026-10-26", "2026-11-02"].map((d) => ({
      sku_id: `sku-${i + 1}`, forecast_date: d, p10: 5, p50: 10, p90: 15,
    })),
  ).flat(),
  ...extra,
});

const skuList = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `sku-${i + 1}`, sku_code: `KURTI-${i + 1}`, description: `Kurti ${i + 1}` }));

const setForecast = (forecast: ForecastResponse) => api.latest.mockImplementation(({ offset = 0, search = "" }) => {
  const allIds = [...new Set(forecast.rows.map((r) => r.sku_id))].filter((id) => {
    const label = (forecast as PersistedForecast).sku_labels?.[id];
    return !search || label?.code.includes(search) || label?.name.includes(search);
  });
  const ids = allIds.slice(offset, offset + 6);
  return Promise.resolve({ forecast: { ...forecast, offset, rows: forecast.rows.filter((r) => ids.includes(r.sku_id)) }, refresh: null, stale: false });
});

it("identifies stale saved results while a refresh is running", async () => {
  api.latest.mockResolvedValue({ forecast: response(1), stale: true,
    refresh: { id: "refresh", status: "running", industry: "fashion" } });
  api.skus.mockResolvedValue(skuList(1));
  renderPage();
  expect(await screen.findByText(/Saved forecast is out of date/)).toBeInTheDocument();
});

it("warns that a failed refresh leaves the saved result unverified against latest data", async () => {
  api.latest.mockResolvedValue({ forecast: response(1), stale: true,
    refresh: { id: "refresh", status: "failed", industry: "fashion", error: "Worker unavailable" } });
  api.skus.mockResolvedValue(skuList(1));
  renderPage();
  expect(await screen.findByText(/Refresh failed; showing the saved forecast/)).toHaveTextContent("may not include your latest data");
});

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <ForecastsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

const axiosError = (status: number, detail: string) =>
  Object.assign(new Error(detail), { isAxiosError: true, response: { status, data: { detail } } });

it("defaults to an available average-sales projection without starting Chronos", async () => {
  api.latest.mockClear(); api.refresh.mockClear();
  api.average.mockResolvedValue({ status: "available", catalogue_skus: 100, eligible_skus: 10,
    missing_skus: 89, unsupported_skus: 1, filtered_skus: 0, projected_units: 0,
    projection_start: "2026-10-27", projection_end: "2027-01-18", source_periods: [], limitations: [], rows: [] });
  renderPage();
  expect(await screen.findByRole("heading", { name: "Average-sales projection" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Chronos model" })).toBeInTheDocument();
  expect(api.latest).not.toHaveBeenCalled();
  expect(api.refresh).not.toHaveBeenCalled();
});

it("shows a selected SKU's location forecast and degraded warning", async () => {
  setForecast(response(2));
  api.skus.mockResolvedValue(skuList(2));
  api.decisions.mockResolvedValue({ decisions: [] });
  api.locationForecast.mockResolvedValue({ run_id: "run-1", degraded: true, unassigned_share: 0.1,
    locations: [{ location_id: "a", code: "alwal", name: "Alwal", p10: [1, 2], p50: [3, 4], p90: [5, 6] },
      { location_id: "b", code: "boduppal", name: "Boduppal", p10: [2, 3], p50: [4, 5], p90: [6, 7] }], reason: null });
  const user = userEvent.setup();
  renderPage();
  await screen.findByText("Kurti 1");
  await user.selectOptions(screen.getByRole("combobox", { name: "Location forecast SKU" }), "sku-1");
  expect(await screen.findByRole("rowheader", { name: "Alwal" })).toBeInTheDocument();
  expect(screen.getByText("Location split incomplete: 10% of sales have no location")).toBeInTheDocument();
  expect(screen.getByTitle("P10 1 – P90 5")).toHaveTextContent("3");
  await user.selectOptions(screen.getByRole("combobox", { name: "Forecast location" }), "boduppal");
  expect(screen.queryByRole("rowheader", { name: "Alwal" })).not.toBeInTheDocument();
  expect(screen.getByRole("rowheader", { name: "Boduppal" })).toBeInTheDocument();
});

describe("Forecasts page (audit F04, F08)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.refresh.mockResolvedValue({ refresh: { id: "job", status: "pending", industry: "fashion", horizon_weeks: 12 }, stale: true });
    api.decisions.mockResolvedValue({ decisions: [] });
    api.skus.mockResolvedValue(skuList(8));
  });

  it("shows the model actually used and every SKU, without invented claims", async () => {
    setForecast(response(6));
    renderPage();

    expect(await screen.findByText("Kurti 6")).toBeInTheDocument();
    for (let i = 1; i <= 6; i += 1) expect(screen.getByText(`Kurti ${i}`)).toBeInTheDocument();
    expect(screen.getAllByText(/Chronos zero-shot/).length).toBeGreaterThan(0);
    expect(screen.getByText(/no external signals applied/i)).toBeInTheDocument();
    // WCAG 1.4.1: the inline link must not be distinguished by colour alone.
    expect(screen.getByRole("link", { name: "Hybrid forecasts" })).toHaveClass("underline");
    expect(screen.getByText(/has not been shown to beat simple baselines on every SKU/)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bTFT\b|DeepAR|Prophet|Live ensemble|12% above|sell-through projected/);
    expect(text).not.toMatch(/Buy now|No purchase needed|Maintain current levels|no urgent action needed|stockout risk is elevated|Place purchase orders/i);
  });

  it("pages through more SKUs than fit on one screen", async () => {
    setForecast(response(8));
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/Showing 1–6 of 8 SKUs/)).toBeInTheDocument();
    expect(screen.queryByText("Kurti 7")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /next page/i }));
    expect(screen.getByText(/Showing 7–8 of 8 SKUs/)).toBeInTheDocument();
    expect(screen.getByText("Kurti 8")).toBeInTheDocument();
  });

  it("filters the forecast table by SKU without changing the saved forecast page", async () => {
    setForecast(response(8));
    renderPage();

    await screen.findByText(/Showing 1–6 of 8 SKUs/);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search forecasts" }), { target: { value: "KURTI-7" } });
    await waitFor(() => expect(api.latest).toHaveBeenLastCalledWith(expect.objectContaining({ search: "KURTI-7", offset: 0 })));
  });

  it("lists SKUs that were not forecast and why", async () => {
    setForecast(
      response(2, { omitted: [{ sku_id: "sku-7", reason: "no_sales_history", observations: 0 }] }),
    );
    renderPage();

    expect(await screen.findByText(/1 SKU not forecast/i)).toBeInTheDocument();
    expect(screen.getByText("KURTI-7")).toBeInTheDocument();
    expect(screen.getByText(/never sold/i)).toBeInTheDocument();
  });

  it("explains a refusal from the service instead of showing a blank page", async () => {
    api.latest.mockRejectedValue(axiosError(422, "Cannot zero-shot forecast: no SKU has the 8 weekly observations"));
    renderPage();

    expect(await screen.findByText(/no SKU has the 8 weekly observations/)).toBeInTheDocument();
  });

  it("never substitutes a decision-derived plan when the service is down", async () => {
    api.latest.mockRejectedValue(axiosError(503, "Forecast service unavailable"));
    api.decisions.mockResolvedValue({ decisions: [
      { sku_id: "sku-1", inputs: { demand_p50_over_window: 70, protection_days: 49 } },
    ] });
    renderPage();

    expect(await screen.findByText(/Forecast service unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/not a model forecast/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Kurti 1")).not.toBeInTheDocument();
  });
});


it("shows persisted age and actual horizon while a different horizon refreshes", async () => {
  setForecast(response(2, { horizon_weeks: 2 }));
  api.refresh.mockRejectedValue(axiosError(503, "Queue unavailable"));
  renderPage();
  expect(await screen.findByText(/Generated 2 hours ago/)).toBeInTheDocument();
  expect(screen.getByText(/Saved forecast: 2 weeks/)).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByText("Forecast settings"));
  await user.click(screen.getByRole("button", { name: /Refresh forecast/i }));
  expect(await screen.findByText(/Queue unavailable/)).toBeInTheDocument();
  expect(screen.getByText("Kurti 1")).toBeInTheDocument();
  expect(api.generate).not.toHaveBeenCalled();
});

it("shows generation status for an empty workspace only after queue acceptance", async () => {
  api.latest.mockResolvedValue({ forecast: null, stale: true, refresh: { id: "job", status: "pending" } });
  renderPage();
  expect(await screen.findByText(/Your first forecast is queued/)).toBeInTheDocument();
  expect(api.generate).not.toHaveBeenCalled();
});

it("returns to the latest run's first page after a refresh completes during pagination", async () => {
  const old = response(8);
  const completed = response(2, { run_id: "new-run" });
  let done = false;
  api.latest.mockImplementation(({ offset = 0, run_id }) => {
    const forecast = done && !run_id ? completed : old;
    const ids = [...new Set(forecast.rows.map((r) => r.sku_id))].slice(offset, offset + 6);
    return Promise.resolve({ forecast: { ...forecast, offset, rows: forecast.rows.filter((r) => ids.includes(r.sku_id)) },
      refresh: { id: "job", status: done ? "completed" : "running", base_run_id: done ? "new-run" : "run-1" }, stale: false });
  });
  renderPage();
  expect(await screen.findByText(/Showing 1–6 of 8 SKUs/)).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /next page/i }));
  expect(await screen.findByText(/Showing 7–8 of 8 SKUs/)).toBeInTheDocument();
  done = true;
  expect(await screen.findByText(/Showing 1–2 of 2 SKUs/, {}, { timeout: 5000 })).toBeInTheDocument();
});

it("keeps pagination usable when the saved run is newer than an old completed refresh", async () => {
  const forecast = response(8, { run_id: "newer-legacy-run" });
  api.latest.mockImplementation(({ offset = 0 }) => {
    const ids = [...new Set(forecast.rows.map((r) => r.sku_id))].slice(offset, offset + 6);
    return Promise.resolve({ forecast: { ...forecast, offset, rows: forecast.rows.filter((r) => ids.includes(r.sku_id)) },
      refresh: { id: "old-job", status: "completed", base_run_id: "older-run" }, stale: false });
  });
  renderPage();
  await screen.findByText(/Showing 1–6 of 8 SKUs/);
  await userEvent.setup().click(screen.getByRole("button", { name: /next page/i }));
  expect(await screen.findByText(/Showing 7–8 of 8 SKUs/)).toBeInTheDocument();
});

it("explains when this industry is waiting behind another tenant forecast", async () => {
  api.latest.mockResolvedValue({ forecast: null, stale: true,
    refresh: { id: "electronics-job", industry: "electronics", status: "running" } });
  renderPage();
  expect(await screen.findByText(/Waiting for another forecast to finish/)).toBeInTheDocument();
  expect(screen.queryByText(/Generating your first forecast/)).not.toBeInTheDocument();
});
