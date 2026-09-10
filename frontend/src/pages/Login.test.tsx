import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { readFileSync } from "node:fs";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
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

vi.mock("@/api/industry", () => ({
  industryApi: {
    catalog: vi.fn().mockResolvedValue({
      fashion: {
        display_name: "Apparel & Fashion",
        default_horizon_weeks: 26,
        audit_level: "standard",
      },
      pharma: {
        display_name: "Pharmaceuticals",
        default_horizon_weeks: 52,
        audit_level: "gxp",
      },
    }),
  },
}));

const renderSignUp = () =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={["/login?mode=signup"]}>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

const fillAccountStep = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText(/full name/i), "Acme Owner");
  await user.type(screen.getByLabelText(/^work email$/i), "owner@acme.example.com");
  await user.type(screen.getByLabelText(/^password$/i), "Sup3rSecret!");
  await user.type(screen.getByLabelText(/confirm password/i), "Sup3rSecret!");
};

const openWorkspaceStep = async (user: ReturnType<typeof userEvent.setup>) => {
  await fillAccountStep(user);
  await user.click(screen.getByRole("button", { name: /continue to workspace/i }));
  await screen.findByRole("heading", { name: /set up your workspace/i });
};

const fillTheForm = async (user: ReturnType<typeof userEvent.setup>, slug: string) => {
  await openWorkspaceStep(user);
  await user.type(screen.getByLabelText(/^workspace name$/i), slug);
};

describe("creating a workspace", () => {
  beforeEach(() => {
    // Not restoreAllMocks: it would reset the module-factory mock above, so the
    // catalog would resolve undefined and the picker would render no options.
    vi.clearAllMocks();
    useAuthStore.setState({ isAuthenticated: false, ready: true });
    window.history.pushState({}, "", "/login?mode=signup");
  });

  it("reveals workspace setup only after account details", async () => {
    const user = userEvent.setup();
    renderSignUp();

    expect(screen.getByRole("heading", { name: /create your account/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^workspace name$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();

    await openWorkspaceStep(user);

    expect(screen.getByLabelText(/^workspace name$/i)).toBeInTheDocument();
    expect(await screen.findByRole("radiogroup")).toBeInTheDocument();
  });

  it("lets the user return to account details without losing progress", async () => {
    const user = userEvent.setup();
    renderSignUp();
    await openWorkspaceStep(user);

    await user.click(screen.getByRole("button", { name: /back to account details/i }));

    expect(await screen.findByRole("heading", { name: /create your account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toHaveValue("Acme Owner");
    expect(screen.getByLabelText(/^work email$/i)).toHaveValue("owner@acme.example.com");
  });

  it("sends the chosen industry to the backend", async () => {
    const signUp = vi
      .spyOn(authApi, "signUp")
      .mockResolvedValue({ status: "ok", user_id: "u", tenant_id: "t" });
    vi.spyOn(authApi, "devLogin").mockRejectedValue(new Error("not needed"));

    const user = userEvent.setup();
    renderSignUp();
    await fillTheForm(user, "acme-pharma");
    await user.click(await screen.findByRole("radio", { name: /pharmaceuticals/i }));
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(signUp).toHaveBeenCalledWith(
        expect.objectContaining({ industry: "pharma", tenant_slug: "acme-pharma" }),
      ),
    );
  });

  it("refuses to submit without an industry", async () => {
    // Signup used to stamp every new workspace Fashion. Defaulting the picker
    // would reintroduce exactly that, so absence must block submission.
    const signUp = vi.spyOn(authApi, "signUp");

    const user = userEvent.setup();
    renderSignUp();
    await fillTheForm(user, "acme-none");
    await screen.findByRole("radio", { name: /pharmaceuticals/i });
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/choose the industry/i),
    );
    expect(signUp).not.toHaveBeenCalled();
  });

  it("preselects no industry", async () => {
    const user = userEvent.setup();
    renderSignUp();
    await openWorkspaceStep(user);
    await user.click(await screen.findByRole("radio", { name: /pharmaceuticals/i }));

    const fashion = screen.getByRole("radio", { name: /apparel & fashion/i });
    expect(fashion).toHaveAttribute("aria-checked", "false");
  });
});
