import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
vi.mock("@/hooks/useWebSocket", () => ({ useWebSocket: () => ({ subscribe: () => () => {} }) }));
import { HybridForecastsPage } from "./HybridForecasts";

it("labels hybrid output as scenario-only and disables operational alerts", () => {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><HybridForecastsPage /></MemoryRouter></QueryClientProvider>);
  expect(screen.getByText(/Scenario only/)).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /Generate shortage alerts/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Run scenario" })).toBeInTheDocument();
});
