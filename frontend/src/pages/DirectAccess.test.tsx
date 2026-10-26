import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { LoginPage } from "@/pages/Login";
import { useAuthStore } from "@/stores/auth";
import App from "@/App";

beforeEach(() => {
  useAuthStore.setState({ isAuthenticated: false, ready: true });
  vi.clearAllMocks();
});

it("does not expose public signup even through an old signup URL", () => {
  window.history.replaceState({}, "", "/login?mode=signup");
  render(<MemoryRouter initialEntries={["/login?mode=signup"]}><LoginPage /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /create account/i })).not.toBeInTheDocument();
  expect(screen.getByText(/invitation/i)).toBeInTheDocument();
});

it("opens sign-in directly when an unauthenticated user opens the app", async () => {
  useAuthStore.setState({ bootstrap: vi.fn() });
  window.history.replaceState({}, "", "/");
  render(<App />);
  expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
  expect(window.location.pathname).toBe("/login");
});
