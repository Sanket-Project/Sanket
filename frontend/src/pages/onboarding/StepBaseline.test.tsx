import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ health: vi.fn(), refresh: vi.fn(), latest: vi.fn(), hybrid: vi.fn() }));
vi.mock("@/api/forecasts", () => ({ forecastsApi: api }));
vi.mock("@/api/hybridForecast", () => ({ hybridForecastApi: { create: api.hybrid, get: vi.fn() } }));
import { StepBaseline } from "./StepBaseline";

it("starts an operational baseline rather than an unvalidated trend scenario", async () => {
  api.health.mockResolvedValue({ status: "ok" });
  api.refresh.mockResolvedValue({ refresh: { id: "r1", status: "pending" }, stale: true });
  api.latest.mockResolvedValue({ refresh: { id: "r1", status: "pending" }, forecast: null, stale: true });
  render(<QueryClientProvider client={new QueryClient()}><StepBaseline thisStep="baseline" save={vi.fn()} /></QueryClientProvider>);
  const button = screen.getByRole("button", { name: "Generate baseline" });
  await waitFor(() => expect(button).toBeEnabled());
  expect(api.refresh).not.toHaveBeenCalled();
  await userEvent.click(button);
  await waitFor(() => expect(api.refresh).toHaveBeenCalledWith({ force_zero_shot: true }));
  expect(api.hybrid).not.toHaveBeenCalled();
});
