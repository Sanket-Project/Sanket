import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PortfolioTotals, SimulationResult } from "@/api/scenarios";

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const api = vi.hoisted(() => ({ presets: vi.fn(), simulate: vi.fn(), interpret: vi.fn() }));
vi.mock("@/api/aiInteractive", () => ({ aiInteractiveApi: { interpret: api.interpret } }));
vi.mock("@/hooks/useCommunicationPreferences", () => ({ useCommunicationPreferences: () => ({ data: { preferences: { language: "en" } } }) }));
vi.mock("@/api/scenarios", async (orig) => ({
  ...(await orig<typeof import("@/api/scenarios")>()),
  scenariosApi: api,
}));

import { WhatIfScenarioPage } from "@/pages/WhatIfScenario";

const totals = (over: Partial<PortfolioTotals> = {}): PortfolioTotals => ({
  currency: "INR", skus: 12, demand_units: 1000, shipped_units: 900, short_units: 100,
  fill_rate: 0.9, skus_stocking_out: 2, revenue: null, gross_margin: null, lost_revenue: null,
  avg_inventory_units: 300, peak_inventory_units: 500, units_ordered: 400,
  purchase_spend: null, holding_cost: null, ...over,
});

const result = (over: Partial<SimulationResult> = {}): SimulationResult => ({
  scenario: { name: "Supplier outage (8 weeks)" },
  config: {
    horizon_weeks: 12, requested_horizon_weeks: 26, forecast_weeks_available: 12,
    horizon_capped_reason: "The forecast covers 12 weeks, so the simulation stops at 12 weeks instead of the 26 requested. Weeks beyond the forecast are not invented.",
    review_weeks: 4, holding_cost_pct: 0.25, service_level: 0.97,
  },
  baseline: totals({ fill_rate: 0.95, skus_stocking_out: 1 }),
  result: totals(),
  impact: { fill_rate_pts: -5, revenue: null, gross_margin: null, lost_revenue: null,
    purchase_spend: null, avg_inventory_units: -40, skus_stocking_out: 1 },
  by_sku: [],
  run_id: "run-1",
  skus_simulated: 12,
  stock_coverage: { skus_with_recorded_stock: 10, skus_total: 12 },
  valuation_coverage: { skus_with_cost: 0, skus_with_price: 12, skus_total: 12 },
  readiness: {
    forecast_run_id: "run-1", forecast_completed_at: "2026-10-06T00:00:00Z", forecast_age_days: 20,
    forecast_stale: true, skus_missing_stock: ["A", "B"], skus_stale_stock: [],
    skus_lead_time_assumed: ["A", "B", "C"], skus_missing_cost: Array.from({ length: 12 }, (_, i) => `S${i}`),
    skus_missing_price: [], assumed_lead_time_days: 14, advisory: true,
  },
  ...over,
});

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><WhatIfScenarioPage /></MemoryRouter>
    </QueryClientProvider>,
  );

describe("Scenario simulator (deep audit F3, F6, F7, F12)", () => {
  beforeEach(() => {
    api.presets.mockResolvedValue({ presets: [] });
    api.simulate.mockResolvedValue(result());
  });

  it("requests an optional explanation only when the user runs a reviewed scenario", async () => {
    api.simulate.mockClear();
    renderPage();
    await screen.findByText("Gross margin");
    expect(api.simulate.mock.calls[0][0].explain_ai).toBeUndefined();
    await userEvent.click(screen.getByRole("checkbox", { name: "Include an AI explanation of engine results" }));
    await userEvent.click(screen.getByRole("button", { name: "Run simulation" }));
    expect(api.simulate.mock.calls.at(-1)?.[0].explain_ai).toBe(true);
  });

  it("settles the initial simulation and enables reviewed runs under StrictMode", async () => {
    api.simulate.mockClear();
    render(<StrictMode><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><WhatIfScenarioPage /></MemoryRouter>
    </QueryClientProvider></StrictMode>);
    await screen.findByText("Gross margin");
    expect(screen.getByRole("button", { name: "Run simulation" })).toBeEnabled();
    expect(api.simulate).toHaveBeenCalledTimes(1);
  });

  it("applies interpreted demand without retaining an unrelated preset outage", async () => {
    api.interpret.mockResolvedValue({ state: "success", assumptions: { demand_shock_pct: 20 }, evidence: [{ field: "demand_shock_pct", span: "Demand increases by 20%", value: 20 }], unresolved: [] });
    renderPage();
    await screen.findByText("Gross margin");
    await userEvent.type(screen.getByRole("textbox", { name: "Describe a scenario" }), "Demand increases by 20%");
    await userEvent.click(screen.getByRole("button", { name: "Interpret assumptions" }));
    await screen.findByRole("spinbutton", { name: "Demand change (%)" });
    await userEvent.click(screen.getByRole("button", { name: "Apply reviewed assumptions" }));
    await userEvent.click(screen.getByRole("button", { name: "Run simulation" }));
    expect(api.simulate.mock.calls.at(-1)?.[0].demand_shock_pct).toBe(20);
    expect(api.simulate.mock.calls.at(-1)?.[0].supplier_outage_weeks).toBe(0);
  });

  it("withholds margin and spend when unit costs are unknown", async () => {
    renderPage();

    await screen.findByText("Gross margin");
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/12 of 12 SKUs missing unit cost/)).toBeInTheDocument();
    expect(screen.queryByText("₹0")).not.toBeInTheDocument();
  });

  it("labels a run on stale or missing inputs as advisory and says why", async () => {
    renderPage();

    expect(await screen.findByText("Advisory")).toBeInTheDocument();
    expect(screen.getByText(/forecast completed 20 days ago/i)).toBeInTheDocument();
    expect(screen.getByText(/2 SKUs have no recorded stock/i)).toBeInTheDocument();
    expect(screen.getByText(/3 SKUs use the assumed 14-day lead time/i)).toBeInTheDocument();
  });

  it("explains that the horizon was capped to the forecast and caps the slider", async () => {
    renderPage();

    expect(await screen.findByText(/simulation stops at 12 weeks/)).toBeInTheDocument();
    const horizon = screen.getByRole("slider", { name: "Horizon" });
    expect(horizon).toHaveAttribute("max", "12");
    expect(horizon).toHaveValue("12");
  });

  it("lets the lever column shrink so controls cannot overflow a phone", async () => {
    renderPage();

    const levers = await screen.findByText("Levers");
    expect(levers.closest("[data-layout='levers']")).toHaveClass("min-w-0");
  });
});
