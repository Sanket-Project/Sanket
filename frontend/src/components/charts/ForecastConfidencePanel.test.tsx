import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/api/forecasts", () => ({ forecastConfidenceApi: api }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
import { ForecastConfidencePanel } from "./ForecastConfidencePanel";

const ready = { industry: "fashion", run_id: "r", scored: 1, portfolio_confidence: 78,
  skus: [{ sku_id: "A", sku_code: "A", confidence: 78, band: "moderate", reasons: [], deductions: [] }] };
const renderPanel = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ForecastConfidencePanel /></QueryClientProvider>);

beforeEach(() => api.list.mockReset());

it("announces a request error and retries instead of claiming there is no data", async () => {
  api.list.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(ready);
  renderPanel();
  expect(await screen.findByRole("alert")).toHaveTextContent("Readiness unavailable");
  expect(screen.queryByText("No readiness scores yet")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Forecast data readiness")).toBeInTheDocument();
  expect(api.list).toHaveBeenCalledTimes(2);
});

it("describes readiness on a 100 point scale without a probability claim", async () => {
  api.list.mockResolvedValue(ready);
  renderPanel();
  expect(await screen.findByText("Forecast data readiness")).toBeInTheDocument();
  expect(screen.getByText(/not a probability/)).toBeInTheDocument();
  expect(screen.queryByText("78%")).not.toBeInTheDocument();
  expect(screen.getAllByText("78/100")).toHaveLength(2);
});

it("discloses that the detail list is limited while the portfolio includes every score", async () => {
  api.list.mockResolvedValue({ ...ready, scored: 51 });
  renderPanel();
  expect(await screen.findByText(/Showing 1 of 51 scored SKUs/)).toBeInTheDocument();
  expect(screen.getByText(/Portfolio score includes all 51/)).toBeInTheDocument();
});
