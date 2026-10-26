import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ForecastResponse } from "@/types/api";

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one to mount.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const api = vi.hoisted(() => ({
  generate: vi.fn(),
  decisions: vi.fn(),
  skus: vi.fn(),
}));

vi.mock("@/api/forecasts", () => ({
  forecastsApi: { generate: api.generate },
  forecastConfidenceApi: { list: vi.fn().mockResolvedValue({ industry: "fashion", run_id: null, scored: 0, skus: [] }) },
}));
vi.mock("@/api/decisions", () => ({ decisionsApi: { list: api.decisions } }));
vi.mock("@/api/skus", () => ({ skusApi: { list: api.skus } }));
vi.mock("@/api/export", () => ({ exportApi: { forecastXlsx: vi.fn(), signalsCsv: vi.fn() } }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { ForecastsPage } from "@/pages/Forecasts";

const response = (n: number, extra: Partial<ForecastResponse> = {}): ForecastResponse => ({
  run_id: "run-1",
  n_predictions: n * 2,
  source: "chronos_zero_shot",
  context_source: "database",
  n_series: n,
  calendar: "W-MON-UTC",
  history_end: "2026-10-26",
  first_forecast_week: "2026-10-26",
  omitted: [],
  rows: Array.from({ length: n }, (_, i) =>
    ["2026-10-26", "2026-11-02"].map((d) => ({
      sku_id: `sku-${i + 1}`, forecast_date: d, p10: 5, p50: 10, p90: 15,
    })),
  ).flat(),
  ...extra,
});

const skuList = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `sku-${i + 1}`, sku_code: `KURTI-${i + 1}`, description: `Kurti ${i + 1}` }));

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

describe("Forecasts page (audit F04, F08)", () => {
  beforeEach(() => {
    api.decisions.mockResolvedValue({ decisions: [] });
    api.skus.mockResolvedValue(skuList(8));
  });

  it("shows the model actually used and every SKU, without invented claims", async () => {
    api.generate.mockResolvedValue(response(6));
    renderPage();

    expect(await screen.findByText("Kurti 6")).toBeInTheDocument();
    for (let i = 1; i <= 6; i += 1) expect(screen.getByText(`Kurti ${i}`)).toBeInTheDocument();
    expect(screen.getAllByText(/Chronos zero-shot/).length).toBeGreaterThan(0);
    expect(screen.getByText(/no external signals applied/i)).toBeInTheDocument();
    expect(screen.getByText(/has not been shown to beat simple baselines on every SKU/)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bTFT\b|DeepAR|Prophet|Live ensemble|12% above|sell-through projected/);
  });

  it("pages through more SKUs than fit on one screen", async () => {
    api.generate.mockResolvedValue(response(8));
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/Showing 1–6 of 8 SKUs/)).toBeInTheDocument();
    expect(screen.queryByText("Kurti 7")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /next page/i }));
    expect(screen.getByText(/Showing 7–8 of 8 SKUs/)).toBeInTheDocument();
    expect(screen.getByText("Kurti 8")).toBeInTheDocument();
  });

  it("lists SKUs that were not forecast and why", async () => {
    api.generate.mockResolvedValue(
      response(2, { omitted: [{ sku_id: "sku-7", reason: "no_sales_history", observations: 0 }] }),
    );
    renderPage();

    expect(await screen.findByText(/1 SKU not forecast/i)).toBeInTheDocument();
    expect(screen.getByText("KURTI-7")).toBeInTheDocument();
    expect(screen.getByText(/never sold/i)).toBeInTheDocument();
  });

  it("explains a refusal from the service instead of showing a blank page", async () => {
    api.generate.mockRejectedValue(axiosError(422, "Cannot zero-shot forecast: no SKU has the 8 weekly observations"));
    renderPage();

    expect(await screen.findByText(/no SKU has the 8 weekly observations/)).toBeInTheDocument();
  });

  it("labels the indicative fallback as not a forecast when the service is down", async () => {
    api.generate.mockRejectedValue(axiosError(503, "Forecast service unavailable"));
    api.decisions.mockResolvedValue({ decisions: [
      { sku_id: "sku-1", inputs: { demand_p50_over_window: 70, protection_days: 49 } },
    ] });
    renderPage();

    expect(await screen.findByText(/Forecast service unavailable/)).toBeInTheDocument();
    expect(screen.getAllByText(/not a model forecast/i).length).toBeGreaterThan(0);
  });
});
