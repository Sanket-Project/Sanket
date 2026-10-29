import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Decision, DecisionListResponse } from "@/api/decisions";

const api = vi.hoisted(() => ({ list: vi.fn(), refresh: vi.fn(), accept: vi.fn(), dismiss: vi.fn() }));
vi.mock("@/api/decisions", () => ({ decisionsApi: api }));
vi.mock("react-hot-toast", () => {
  const t = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() });
  return { default: t };
});
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import toast from "react-hot-toast";
import { DecisionsPage } from "@/pages/Decisions";

const decision = (over: Partial<Decision> = {}): Decision => ({
  id: "d1", sku_id: "s1", sku_code: "KURTI-M", kind: "purchase_order", status: "open",
  urgency: "high", headline: "Raise a purchase order for 60 units", recommended_units: 60,
  baseline_units: 80, accepted_units: null, confidence: 72, confidence_band: "moderate",
  currency: "INR", unit_cost: null, unit_price: 100, reasons: [],
  economics: { currency: "INR", capital_committed: null, revenue_protected: 6000 },
  inputs: {
    lead_time_days: 14, review_period_days: 28, protection_days: 42, service_level: 0.97, z: 1.88,
    demand_p50_over_window: 60, demand_p90_over_window: 72, sigma_over_window: 5,
    safety_stock_units: 9, order_up_to: 69, on_hand_units: 0, reserved_units: 0, inbound_units: 0,
    position_units: 0, days_of_cover: 0, moq: 1, unit_cost: null, unit_price: 100,
    lead_time_assumed: true, forecast_horizon_weeks: 12, holding_cost_pct: 0.25,
  },
  linked_alert_id: null, created_at: null, decided_at: null, expires_at: null,
  ...over,
});

const listOf = (items: Decision[], totals: Partial<DecisionListResponse["totals"]> = {}): DecisionListResponse => ({
  industry: "fashion", status: "open", count: items.length, decisions: items,
  totals: {
    purchase_orders: items.length, units_to_order: 60, capital_committed: null,
    working_capital_released_vs_baseline: null, revenue_protected: 6000, money_complete: false,
    critical: 0, currency: "INR", ...totals,
  },
});

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><DecisionsPage /></MemoryRouter>
    </QueryClientProvider>,
  );

it("labels readiness as points and service levels as unvalidated targets", async () => {
  api.list.mockResolvedValue(listOf([decision()]));
  renderPage();
  expect(await screen.findByText("72/100 readiness")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name:/show working/i}));
  expect(screen.getByText(/target, not a measured guarantee/)).toBeInTheDocument();
  expect(screen.getByText(/independent weekly errors/)).toBeInTheDocument();
  expect(screen.queryByText(/lets you hit the same/)).not.toBeInTheDocument();
});

it("keeps accepted-order details usable when frozen planning inputs are incomplete", async () => {
  api.list.mockResolvedValue(listOf([decision({ status: "accepted", accepted_units: 60, inputs: { unit_cost: 40, lead_time_days: 14 } })]));
  const { container } = renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /show working/i }));
  expect(screen.getByText(/Some saved planning inputs are unavailable/)).toBeInTheDocument();
  expect(container).not.toHaveTextContent("NaN");
  expect(screen.getByRole("button", { name: "Prepare supplier draft" })).toBeInTheDocument();
  expect(api.accept).not.toHaveBeenCalled();
});

it("offers a scoped AI explanation inside the saved decision details", async () => {
  api.list.mockResolvedValue(listOf([decision()]));
  renderPage();
  const working = await screen.findByRole("button", { name: /show working/i });
  expect(working).not.toHaveClass("hidden");
  fireEvent.click(working);
  expect(screen.getByRole("button", { name: "Explain this decision" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Get industry advice" })).toBeInTheDocument();
  expect(screen.getAllByRole("complementary", { name: "AI summary" })).toHaveLength(2);
  expect(api.accept).not.toHaveBeenCalled();
});

it("groups allocation and transfer lines by route and expands frozen network inputs", async () => {
  api.list.mockResolvedValue(listOf([
    decision({ id: "a1", kind: "allocation", source_location_code: "dc", location_code: "alwal", recommended_units: 10 }),
    decision({ id: "a2", kind: "allocation", source_location_code: "dc", location_code: "alwal", recommended_units: 20 }),
    decision({ id: "t1", kind: "transfer", source_location_code: "boduppal", location_code: "alwal", recommended_units: 5,
      inputs: { unit_cost: null, unit_price: null, deficit: 5, excess: 20 }, reasons: [] }),
  ]));
  renderPage();
  expect(await screen.findByText("dc → alwal · 2 lines · 30 units")).toBeInTheDocument();
  expect(screen.getByText("boduppal → alwal · 1 lines · 5 units")).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: "Show working" })[2]);
  expect(await screen.findByText("Deficit")).toBeInTheDocument();
});

it("shows network setup notes after refresh", async () => {
  api.list.mockResolvedValue(listOf([]));
  api.refresh.mockResolvedValue({ generated: 0, skus_evaluated: 0, skipped: [],
    notes: ["No warehouse is defined"], decisions: [], totals: listOf([]).totals });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /recompute from latest forecast/i }));
  expect(await screen.findByText("Network setup needed")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Set up network in Settings" })).toHaveAttribute("href", "/workspace/settings?tab=network");
});

describe("Decisions page (deep audit F3, F6, F8, F14)", () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
  });

  it("reports a failed load instead of 'No open recommendations'", async () => {
    api.list.mockRejectedValue(new Error("503"));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/decisions could not be loaded/i);
    expect(screen.queryByText("No open recommendations")).not.toBeInTheDocument();
  });

  it("shows unknown capital as unavailable, never ₹0", async () => {
    api.list.mockResolvedValue(listOf([decision()]));

    renderPage();

    expect(await screen.findByText("Raise a purchase order for 60 units")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/missing unit cost/i)).toBeInTheDocument();
    expect(screen.queryByText("₹0")).not.toBeInTheDocument();
  });

  it("marks a decision whose lead time was assumed", async () => {
    api.list.mockResolvedValue(listOf([decision()]));

    renderPage();

    expect(await screen.findByText("Lead time assumed (14-day default)")).toBeInTheDocument();
  });

  it("refreshes the queue when the server rejects an accept (e.g. expired)", async () => {
    api.list.mockResolvedValue(listOf([decision()]));
    api.accept.mockRejectedValue({ response: { status: 409, data: { detail: "Recommendation expired" } } });
    renderPage();
    await screen.findByText("Raise a purchase order for 60 units");
    const loads = api.list.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(loads));
  });

  it("records what it can in a bulk accept and reports the rows that were refused", async () => {
    api.list.mockResolvedValue(listOf([decision(), decision({ id: "d2", sku_code: "KURTI-L" })]));
    api.accept.mockImplementation((id: string) =>
      id === "d2"
        ? Promise.reject({ response: { status: 409, data: { detail: "Recommendation expired" } } })
        : Promise.resolve(decision({ status: "accepted" })));
    renderPage();
    await screen.findByText(/KURTI-L/);
    const loads = api.list.mock.calls.length;

    screen.getAllByRole("checkbox").forEach((box) => fireEvent.click(box));
    fireEvent.click(screen.getByRole("button", { name: /accept selected/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/1 recorded.*1 could not/i)));
    expect(api.accept).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(loads));
  });

  it("explains why SKUs were left out after a recompute", async () => {
    api.list.mockResolvedValue(listOf([]));
    api.refresh.mockResolvedValue({
      industry: "fashion", generated: 0, skus_evaluated: 0,
      reason: "No SKU has a current stock position.",
      skipped: [{ sku_code: "KURTI-M", reason: "Stock was last updated 40 days ago." }],
      decisions: [], totals: listOf([]).totals,
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /recompute from latest forecast/i }));

    expect(await screen.findByText(/KURTI-M/)).toBeInTheDocument();
    expect(screen.getByText(/last updated 40 days ago/)).toBeInTheDocument();
  });
});
