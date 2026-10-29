import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ForecastAccuracyResponse } from "@/api/forecastAccuracy";

const api = vi.hoisted(() => ({ list: vi.fn(), anomalies: vi.fn(), backtest: vi.fn() }));
vi.mock("@/components/charts/CategoryBar", () => ({ CategoryBar: () => null }));
vi.mock("@/api/forecastAccuracy", () => ({ forecastAccuracyApi: { list: api.list, anomalies: api.anomalies } }));
vi.mock("@/api/forecasts", () => ({
  forecastsApi: { backtest: api.backtest },
  forecastConfidenceApi: { list: vi.fn().mockResolvedValue({ industry: "fashion", run_id: "r", scored: 1, skus: [] }) },
}));
vi.mock("@/api/salesAnalytics", () => ({ salesAnalyticsApi: { timeseries: vi.fn().mockResolvedValue({ series: [{}] }) } }));
vi.mock("@/api/dataQuality", () => ({ dataQualityApi: { report: vi.fn().mockResolvedValue({ critical: 0, health_score: 90 }) } }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { ForecastAccuracyPage } from "@/pages/ForecastAccuracy";
import { backtestCutoffError } from "@/pages/forecastAccuracyRules";

const excluded = { legacy_calendar: 0, period_not_complete: 0, trained_on_period: 0,
  generated_after_period_start: 0, awaiting_actuals: 0 };

const response = (over: Partial<ForecastAccuracyResponse>): ForecastAccuracyResponse => ({
  industry: "fashion",
  source: "live",
  calendar: "W-MON-UTC",
  basis: "",
  rows: [],
  summary: { points: 0, skus: 0, wape: null, bias_pct: null, coverage_p10_p90: null },
  excluded,
  backtest: { note: "", runs: [] },
  ...over,
});

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <ForecastAccuracyPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("Forecast accuracy (audit F02)", () => {
  it("discloses capped scoring and compares simple rules on matching cohorts", async () => {
    api.list.mockResolvedValue(response({
      rows: [{ sku_id: "s1", sku_code: "A", model_name: "chronos", mape: 20,wape:20,bias_pct:20,coverage_p10_p90:80,n_obs:2,computed_at:null,weeks:[] }],
      truncated: true,
      summary: { points:2,skus:1,wape:20,bias_pct:20,coverage_p10_p90:80,baselines: {
        last_value: { n_obs:2,excluded_missing_history:0,wape:40,forecast_wape:20,wape_skill:0.5 },
        seasonal_naive: { n_obs:0,excluded_missing_history:2,wape:null,forecast_wape:null,wape_skill:null },
      } },
    }));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Accuracy covers a limited subset");
    expect(screen.getByText("Compared with simple forecasts")).toBeInTheDocument();
    expect(screen.getByText(/50.0% less error/)).toBeInTheDocument();
    expect(screen.getByText(/Historical data availability has not been verified/)).toBeInTheDocument();
    expect(screen.getByText(/No matching history/)).toBeInTheDocument();
  });
  it("discloses when the detail response contains only part of the scored cohort", async () => {
    api.list.mockResolvedValue(response({
      rows: [{ sku_id: "s1", sku_code: "A", model_name: "chronos", mape: 20,wape:20,bias_pct:20,coverage_p10_p90:80,n_obs:2,computed_at:null,weeks:[] }],
      scope: { run_limit:60,result_limit:50000,runs_considered:2,results_considered:20,
        runs_truncated:false,results_truncated:false,detail_rows_total:10,detail_rows_returned:1,detail_truncated:true },
    }));
    renderPage();
    expect(await screen.findByText(/Showing 1 of 10 scored SKU-model rows/)).toBeInTheDocument();
  });
  beforeEach(() => {
    api.anomalies.mockResolvedValue({ industry: "fashion", window_days: 90, sku_count: 0, anomalous_skus: [] });
    api.backtest.mockReset();
  });

  it("reports a failed accuracy request instead of empty readiness", async () => {
    api.list.mockRejectedValue(new Error("offline"));
    renderPage();
    expect(await screen.findByText("Accuracy unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Complete the accuracy prerequisites")).not.toBeInTheDocument();
  });

  it("offers an explanation for a flagged SKU without running a backtest", async () => {
    api.list.mockResolvedValue(response({ rows: [{ sku_id: "sku-1", sku_code: "S1", model_name: "chronos_zero_shot", mape: 25, wape: 25, bias_pct: 25, coverage_p10_p90: 100, n_obs: 1, computed_at: null, weeks: [] }] }));
    api.anomalies.mockResolvedValue({ industry: "fashion", window_days: 90, sku_count: 1,
      anomalous_skus: [{ sku_id: "sku-1", anomaly_count: 1, latest_anomaly_date: "2026-10-19", anomaly_rows: [{ ds: "2026-10-19", y: 7, score: 0.9 }] }] });
    renderPage();
    expect(await screen.findByRole("complementary", { name: "AI summary" })).toBeInTheDocument();
    expect(api.backtest).not.toHaveBeenCalled();
  });

  it("rejects invalid calendar dates and current or future weeks", () => {
    const today = new Date("2026-10-26T12:00:00Z");
    expect(backtestCutoffError("2026-02-30", today)).toBe("Enter a valid date.");
    expect(backtestCutoffError("2026-10-26", today)).toMatch(/before the current week/);
    expect(backtestCutoffError("2026-11-02", today)).toMatch(/before the current week/);
    expect(backtestCutoffError("2026-10-19", today)).toBeNull();
  });

  it("shows date-matched production accuracy and why forecasts were left out", async () => {
    api.list.mockResolvedValue(response({
      rows: [{ sku_id: "s1", sku_code: "KURTI-M", model_name: "chronos_zero_shot", mape: 25, wape: 25,
        bias_pct: 25, coverage_p10_p90: 100, n_obs: 1, computed_at: null, weeks: [] }],
      summary: { points: 1, skus: 1, wape: 25, bias_pct: 25, coverage_p10_p90: 100 },
      excluded: { ...excluded, generated_after_period_start: 1, unvalidated_scenario: 2 },
    }));

    renderPage();

    expect(await screen.findByText(/Production accuracy/)).toBeInTheDocument();
    expect(screen.getByText("KURTI-M")).toBeInTheDocument();
    expect(screen.getAllByText("25.0%").length).toBeGreaterThan(0);
    expect(screen.getByText(/1 forecast made after its week had begun/)).toBeInTheDocument();
    expect(screen.getByText(/2 unvalidated scenario forecasts/)).toBeInTheDocument();
  });

  it("reports backtests separately and labels them as made after the fact", async () => {
    api.list.mockResolvedValue(response({
      backtest: { note: "", runs: [{ run_id: "b1", cutoff: "2026-08-31", completed_at: "2026-10-26T09:00:00Z",
        points: 48, skus: 6, wape: 9.1, bias_pct: -2, mape: 10, coverage_p10_p90: 81.3 }] },
    }));

    renderPage();

    expect(await screen.findByText(/Backtest from 31 Aug 2026/)).toBeInTheDocument();
    expect(screen.getByText(/48 points/)).toBeInTheDocument();
    expect(screen.getAllByText(/made after the fact/i).length).toBeGreaterThan(0);
  });

  it("runs a backtest only from a past Monday", async () => {
    api.list.mockResolvedValue(response({}));
    api.backtest.mockResolvedValue({ rows: [] });
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByLabelText(/forecast as if it were/i);
    await user.type(input, "2026-08-30");
    await user.click(screen.getByRole("button", { name: /run backtest/i }));
    expect(screen.getByText(/must be a Monday/i)).toBeInTheDocument();
    expect(api.backtest).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, "2026-08-31");
    await user.click(screen.getByRole("button", { name: /run backtest/i }));
    expect(api.backtest).toHaveBeenCalledWith({ cutoff: "2026-08-31", horizon: 8 });
  });
});
