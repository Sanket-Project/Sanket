import { render, screen } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/components/layout/AppShell", () => ({ AppShell: () => <Outlet /> }));
vi.mock("@/hooks/useWebSocket", () => ({ useWebSocket: () => ({ subscribe: () => () => {} }) }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import App from "@/App";
import { useAuthStore } from "@/stores/auth";

beforeEach(() => {
  useAuthStore.setState({ isAuthenticated: true, ready: true, industry: "fashion", onboarding: null, bootstrap: vi.fn() });
});

// The first render lazily loads the whole Hybrid page module graph, which is slow in jsdom.
it("renders Hybrid Forecasts at /workspace/forecasts/hybrid instead of redirecting", async () => {
  window.history.replaceState({}, "", "/workspace/forecasts/hybrid");
  render(<App />);
  expect(await screen.findByRole("button", { name: "Run scenario" }, { timeout: 20000 })).toBeInTheDocument();
  expect(window.location.pathname).toBe("/workspace/forecasts/hybrid");
}, 30000);
