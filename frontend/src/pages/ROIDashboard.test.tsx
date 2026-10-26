import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RoiLine, RoiSummary } from "@/api/roi";
import { useCurrencyStore } from "@/stores/currency";

const api = vi.hoisted(() => ({ summary: vi.fn() }));
vi.mock("@/api/roi", () => ({ roiApi: api }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { ROIDashboardPage } from "@/pages/ROIDashboard";

const line = (over: Partial<RoiLine>): RoiLine => ({
  key: "k", label: "Line", tier: "estimated_at_approval", value: 0, unit: "currency",
  currency: "INR", values_by_currency: { INR: 0 }, additive: true, basis: "basis",
  evidence_count: 0, details: [], ...over,
});

const summary = (lines: RoiLine[], currencies = ["INR"]): RoiSummary => {
  const tier = (key: RoiLine["tier"], label: string, status: string) => ({
    label, status, lines: lines.filter((l) => l.tier === key),
  });
  return {
    industry: "fashion",
    window_days: 90,
    currency: currencies.length === 1 ? currencies[0] : null,
    currencies,
    tiers: {
      opportunity: tier("opportunity", "Open recommendations — forecast-based estimates of what is at stake", "estimate"),
      estimated_at_approval: tier("estimated_at_approval", "Estimated when you approved — not observed savings", "estimate"),
      observed: tier("observed", "Observed outcomes", "not_measurable"),
    },
    lines,
    adoption: { recommendations_accepted: 1, recommendations_open: 1 },
    caveat: "Approving a recommendation is a decision, not an outcome.",
  };
};

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ROIDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("ROI dashboard (audit F10)", () => {
  beforeEach(() => act(() => useCurrencyStore.setState({ display: "source", manualRate: null })));

  it("labels approval figures as estimates and realised savings as not measurable", async () => {
    api.summary.mockResolvedValue(summary([
      line({ key: "working_capital_vs_baseline", label: "Working capital below baseline", value: 8000,
        values_by_currency: { INR: 8000 } }),
      line({ key: "carrying_cost_implied", label: "Carrying cost implied", value: 230,
        values_by_currency: { INR: 230 }, additive: false }),
      line({ key: "realized_savings", label: "Realised savings", tier: "observed", value: null,
        currency: null, values_by_currency: {}, basis: "No goods receipt is recorded." }),
    ]));

    renderPage();

    expect(await screen.findByText(/Estimated when you approved — not observed savings/)).toBeInTheDocument();
    const realised = screen.getByText("Realised savings").closest("button");
    expect(realised?.textContent).toMatch(/Not measurable yet/);
    expect(screen.getByText(/derived — not additional/i)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/not modelled, not projected|Total value realised|What SANKET saved you/i);
  });

  it("shows money per currency rather than one total", async () => {
    api.summary.mockResolvedValue(summary([
      line({ key: "working_capital_vs_baseline", label: "Working capital below baseline", value: null,
        currency: null, values_by_currency: { INR: 8000, USD: 8000 } }),
    ], ["INR", "USD"]));

    renderPage();

    expect(await screen.findByText("₹8K · $8K")).toBeInTheDocument();
  });
});
