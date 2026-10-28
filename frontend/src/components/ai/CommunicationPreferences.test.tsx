import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import { CommunicationPreferences } from "./CommunicationPreferences";

const api = vi.hoisted(() => ({ preferences: vi.fn(), save: vi.fn() }));
vi.mock("@/api/communications", () => ({ communicationsApi: api }));
vi.mock("@/stores/auth", () => ({ useAuthStore: (selector: (s: { tenantId: string; userId: string }) => unknown) => selector({ tenantId: "synthetic-workspace", userId: "synthetic-member" }) }));

it("loads persisted language and only opts in after saving, showing unavailable delivery honestly", async () => {
  api.preferences.mockResolvedValue({ preferences: { language: "te", weekly_enabled: false, timezone: "Asia/Kolkata", send_hour: 8 }, next_delivery: null, delivery_available: false, scheduling_available: false, last_delivery: null });
  api.save.mockImplementation(async (preferences) => ({ preferences, delivery_available: false, scheduling_available: false, next_delivery: null, last_delivery: null }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CommunicationPreferences /></QueryClientProvider>);
  expect(await screen.findByLabelText("Summary language")).toHaveValue("te");
  expect(screen.getByText(/Email delivery unavailable/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText(/Email me a weekly/));
  expect(api.save).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Save communication preferences" }));
  await waitFor(() => expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ language: "te", weekly_enabled: true })));
});
