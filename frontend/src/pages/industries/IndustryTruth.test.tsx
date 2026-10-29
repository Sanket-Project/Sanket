import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { industryApi } from "@/api/industry";
import { useAuthStore } from "@/stores/auth";
import { FashionDashboard } from "./FashionDashboard";
import { ElectronicsDashboard } from "./ElectronicsDashboard";
import { AgrocenterdDashboard } from "./AgrocenterdDashboard";
import { HardwareDashboard } from "./HardwareDashboard";
import { PharmaDashboard } from "./PharmaDashboard";

vi.mock("@/api/industry", () => ({ industryApi: { overview: vi.fn() } }));
vi.mock("@/api/forecasts", () => ({ forecastsApi: { generate: vi.fn().mockResolvedValue({ rows: [] }) } }));
vi.mock("@/api/pharma", () => ({ pharmaApi: { expiringBatches: vi.fn().mockResolvedValue({ batches: [], count: 0 }) } }));

beforeEach(() => {
  useAuthStore.setState({ isAuthenticated: true, industry: "fashion" });
  vi.mocked(industryApi.overview).mockResolvedValue({ industry: "fashion", kpis: { active_skus: 7, validated_signals: 0, active_weather_signals: 0, validated_regulatory_signals: 0, active_price_signals: 0, validated_supply_signals: 0, logistics_disruption_signals: 0, competitor_price_signals: 0, batches_released: 0, batches_in_quarantine: 0, batches_expiring_in_90_days: 0, active_regulatory_signals: 0 }, top_categories: [], forecast_horizon_weeks: 12, active_models: [] });
});

for (const Screen of [FashionDashboard, ElectronicsDashboard, AgrocenterdDashboard, HardwareDashboard, PharmaDashboard]) {
  it(`${Screen.name} shows source-backed metrics without invented health, growth or signals`, async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Screen /></MemoryRouter></QueryClientProvider>);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByText(/\d+% confidence/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Quiet Luxury|TSMC 5nm|Container rates up|La Niña/)).not.toBeInTheDocument();
    for (const invented of ["84%", "68%", "76%", "82%", "91%", "74%", "95%", "18 wks", "Week 6"]) expect(screen.queryByText(invented, { exact: true })).not.toBeInTheDocument();
  });
}

it("shows a failed overview as unavailable instead of an endless loader", async () => {
  vi.mocked(industryApi.overview).mockRejectedValue(new Error("Source unavailable"));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><FashionDashboard /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText("Industry overview unavailable")).toBeInTheDocument();
});
