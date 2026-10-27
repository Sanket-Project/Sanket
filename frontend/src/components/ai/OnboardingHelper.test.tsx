import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { OnboardingHelper } from "./OnboardingHelper";

const api = vi.hoisted(() => ({ summary: vi.fn() }));
vi.mock("@/api/ai", () => ({ aiApi: api }));

it("asks for catalog-grounded setup help without sending credentials", async () => {
  api.summary.mockResolvedValue({ state: "disabled", blocks: [] });
  render(<QueryClientProvider client={new QueryClient()}><OnboardingHelper /></QueryClientProvider>);
  await userEvent.type(screen.getByLabelText("Connector question"), "How do I connect Shopify?");
  await userEvent.click(screen.getByRole("button", { name: "Generate AI summary" }));
  await waitFor(() => expect(api.summary).toHaveBeenCalledWith("onboarding", undefined, "How do I connect Shopify?"));
});
