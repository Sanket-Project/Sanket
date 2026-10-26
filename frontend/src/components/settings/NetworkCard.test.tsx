import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ list: vi.fn(), update: vi.fn() }));
vi.mock("@/api/locations", () => ({ locationsApi: api }));
import { NetworkCard } from "./NetworkCard";

const locations = [
  { id: "dc", code: "dc", name: "Central DC", kind: "warehouse", parent_location_id: null,
    lead_time_days_from_parent: null, is_active: true },
  { id: "a", code: "a", name: "Alwal", kind: "unconfirmed", parent_location_id: null,
    lead_time_days_from_parent: null, is_active: true },
];
const missing = ["Location 'a' kind is not confirmed", "Store 'a' has no supplying warehouse"];
const renderCard = () => render(<QueryClientProvider client={new QueryClient({
  defaultOptions: { queries: { retry: false } },
})}><NetworkCard /></QueryClientProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue({ locations, network: { allocation_ready: false, transfers_ready: false, missing } });
  api.update.mockResolvedValue({ location: locations[1], network: { missing } });
});

it("lists editable network fields with only warehouse parent choices", async () => {
  renderCard();
  await screen.findByText("Alwal");
  expect(screen.getByRole("combobox", { name: "Kind for Alwal" })).toBeInTheDocument();
  const parent = screen.getByRole("combobox", { name: "Supplied by for Alwal" });
  expect(within(parent).getByRole("option", { name: "Central DC" })).toBeInTheDocument();
  expect(within(parent).queryByRole("option", { name: "Alwal" })).not.toBeInTheDocument();
  expect(screen.getByRole("spinbutton", { name: "Lead time for Alwal" })).toBeInTheDocument();
  for (const message of missing) expect(screen.getByText(message)).toBeInTheDocument();
});

it("updates a kind and refetches the network", async () => {
  renderCard();
  const kind = await screen.findByRole("combobox", { name: "Kind for Alwal" });
  const calls = api.list.mock.calls.length;
  fireEvent.change(kind, { target: { value: "warehouse" } });
  await waitFor(() => expect(api.update).toHaveBeenCalledWith("a", { kind: "warehouse" }));
  await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(calls));
});

it("shows allocation readiness", async () => {
  api.list.mockResolvedValue({ locations, network: { allocation_ready: true, transfers_ready: true, missing: [] } });
  renderCard();
  expect(await screen.findByText("Allocation ready")).toBeInTheDocument();
});

it("warns when unassigned sales make the location split incomplete", async () => {
  api.list.mockResolvedValue({ locations, network: { allocation_ready: true, transfers_ready: true,
    missing: [], degraded: true, unassigned_share: 0.2 } });
  renderCard();
  expect(await screen.findByText("Location split incomplete: 20% of sales have no location")).toBeInTheDocument();
});
