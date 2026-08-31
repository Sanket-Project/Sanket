import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { LoginPage } from "@/pages/Login";
import { useAuthStore } from "@/stores/auth";

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

const fillTheForm = async (user: ReturnType<typeof userEvent.setup>, slug: string) => {
  await user.type(screen.getByLabelText(/full name/i), "Acme Owner");
  await user.type(screen.getByLabelText(/^workspace$/i), slug);
  await user.type(screen.getByLabelText(/^email$/i), `owner@${slug}.example.com`);
  await user.type(screen.getByLabelText(/^password$/i), "Sup3rSecret!");
  await user.type(screen.getByLabelText(/confirm password/i), "Sup3rSecret!");
};

describe("creating a workspace", () => {
  beforeEach(() => {
    // Not restoreAllMocks: it would reset the module-factory mock above, so the
    // catalog would resolve undefined and the picker would render no options.
    vi.clearAllMocks();
    useAuthStore.setState({ isAuthenticated: false, ready: true });
    window.history.pushState({}, "", "/login?mode=signup");
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
      expect(screen.getByText(/choose the industry/i)).toBeInTheDocument(),
    );
    expect(signUp).not.toHaveBeenCalled();
  });

  it("preselects no industry", async () => {
    const user = userEvent.setup();
    renderSignUp();
    await user.click(await screen.findByRole("radio", { name: /pharmaceuticals/i }));

    const fashion = screen.getByRole("radio", { name: /apparel & fashion/i });
    expect(fashion).toHaveAttribute("aria-checked", "false");
  });
});
