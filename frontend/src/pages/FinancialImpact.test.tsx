import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCurrencyStore } from "@/stores/currency";

const api = vi.hoisted(() => ({ impact: vi.fn(), costAnalysis: vi.fn() }));
vi.mock("@/api/financial", () => ({ financialApi: api }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { FinancialImpactPage } from "@/pages/FinancialImpact";

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <FinancialImpactPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

const row = (currency: string) => ({
  sku_id: currency, sku_code: `K-${currency}`, currency, unit_price: 500, unit_cost: 200,
  p50_demand: 10, p90_demand: 14, safety_stock: 50, revenue_at_risk: 2000,
  excess_inventory_cost: 0, total_impact: 2000,
});

describe("Financial impact currency (audit F03)", () => {
  beforeEach(() => {
    act(() => useCurrencyStore.setState({ display: "source", manualRate: null }));
    api.costAnalysis.mockResolvedValue({ industry: "fashion", holding_cost_pct: 0.25, currency: null,
      totals: { annual_holding_cost: 0, stockout_exposure_cost: 0, total_impact: 0 },
      totals_by_currency: {}, skus: [] });
  });

  it("shows rupee exposure in rupees, not dollars", async () => {
    api.impact.mockResolvedValue({ industry: "fashion", horizon_weeks: 12, currency: "INR",
      total_revenue_at_risk: 2000, total_excess_cost: 0, net_impact: 2000,
      totals_by_currency: { INR: { revenue_at_risk: 2000, excess_inventory_cost: 0, total_impact: 2000 } },
      by_sku: [row("INR")] });

    renderPage();

    expect((await screen.findAllByText("₹2K")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/\$2K/)).not.toBeInTheDocument();
  });

  it("shows each currency's total when exposure is in several", async () => {
    api.impact.mockResolvedValue({ industry: "fashion", horizon_weeks: 12, currency: null,
      total_revenue_at_risk: null, total_excess_cost: null, net_impact: null,
      totals_by_currency: {
        INR: { revenue_at_risk: 2000, excess_inventory_cost: 0, total_impact: 2000 },
        USD: { revenue_at_risk: 2000, excess_inventory_cost: 0, total_impact: 2000 },
      },
      by_sku: [row("INR"), row("USD")] });

    renderPage();

    expect((await screen.findAllByText("₹2K · $2K")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/4K/)).not.toBeInTheDocument();
  });
});
