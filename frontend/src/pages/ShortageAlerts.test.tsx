import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { ShortageAlertsPage } from "./ShortageAlerts";

vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
vi.mock("@/api/shortageAlerts", () => ({ shortageAlertsApi: {
  list: vi.fn().mockResolvedValue([{ id: "alert-1", title: "Low cover", message: "Review stock", severity: "warning",
    status: "open", risk_score: 0.7, coverage_days: null, trend_score: null, fired_at: "2026-10-27T00:00:00Z" }]),
  listRules: vi.fn().mockResolvedValue([]), acknowledge: vi.fn(), resolve: vi.fn(),
} }));
vi.mock("@/api/decisions", () => ({ decisionsApi: { list: vi.fn().mockResolvedValue({ decisions: [] }) } }));

it("offers an optional explanation while retaining the original risk and acknowledgment", async () => {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ShortageAlertsPage /></MemoryRouter></QueryClientProvider>);
  await screen.findByText("Low cover");
  expect(screen.getByRole("complementary", { name: "AI summary" })).toBeInTheDocument();
  expect(screen.getByText("Risk: 70%")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Acknowledge" })).toBeInTheDocument();
});
