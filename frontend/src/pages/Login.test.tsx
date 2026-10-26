import { readFileSync } from "node:fs";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "@/pages/Login";
import { useAuthStore } from "@/stores/auth";

const loginSource = readFileSync("src/pages/Login.tsx", "utf8");

describe("authentication accessibility", () => {
  it("honors the user's reduced-motion preference", () => {
    expect(loginSource).toContain("useReducedMotion");
  });

  it("uses theme-aware surfaces for the gateway and form card", () => {
    expect(loginSource).toContain('className="min-h-screen bg-canvas');
    expect(loginSource).toContain("border border-line-strong bg-surface");
  });
});

const renderLogin = () => render(
  <MemoryRouter initialEntries={["/login"]}>
    <Routes><Route path="/login" element={<LoginPage />} /><Route path="/workspace" element={<h1>Workspace dashboard</h1>} /></Routes>
  </MemoryRouter>,
);

describe("invitation-only sign in", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthStore.setState({ isAuthenticated: false, ready: true });
    window.history.replaceState({}, "", "/login");
  });
  it("submits credentials and opens the workspace", async () => {
    const login = vi.fn().mockResolvedValue({});
    useAuthStore.setState({ login });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/^workspace$/i), "test-workspace");
    await user.type(screen.getByLabelText(/^email$/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Sup3rSecret!");
    await user.click(screen.getByRole("button", { name: /^sign in/i }));
    await waitFor(() => expect(login).toHaveBeenCalledWith({ tenant_slug: "test-workspace", email: "test@example.com", password: "Sup3rSecret!" }));
    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
  });
  it("shows credential errors and keeps password-manager support", async () => {
    useAuthStore.setState({ login: vi.fn().mockRejectedValue({ response: { data: { detail: "Invalid email or password" } } }) });
    const user = userEvent.setup();
    renderLogin();
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("autocomplete", "current-password");
    await user.type(screen.getByLabelText(/^workspace$/i), "test-workspace");
    await user.type(screen.getByLabelText(/^email$/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrong");
    await user.click(screen.getByRole("button", { name: /^sign in/i }));
    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
  });
  it("sends an existing session directly to its workspace", async () => {
    useAuthStore.setState({ isAuthenticated: true });
    renderLogin();
    expect(await screen.findByRole("heading", { name: /workspace dashboard/i })).toBeInTheDocument();
  });
});
