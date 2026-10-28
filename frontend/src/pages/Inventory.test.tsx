import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ overview: vi.fn(), upsert: vi.fn(), skuList: vi.fn(), parseFile: vi.fn(), validateRows: vi.fn() }));
vi.mock("@/api/inventory", () => ({
  inventoryApi: api, validateInventoryRows: api.validateRows, downloadInventoryTemplate: vi.fn(),
}));
vi.mock("@/api/skus", () => ({ skusApi: { list: api.skuList } }));
vi.mock("@/utils/csvImport", () => ({ parseFile: api.parseFile }));
vi.mock("@/api/export", () => ({ exportApi: { inventoryCsv: vi.fn() } }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
vi.mock("@/components/ui/ImportModal", () => ({ ImportModal: ({ open, onParse, onImport }: { open: boolean; onParse: (file: File) => Promise<unknown>; onImport: (rows: unknown[], callback: () => void) => Promise<unknown> }) => open ? <div><button onClick={() => void onParse(new File(["csv"], "stock.csv"))}>Parse test file</button><button onClick={() => void onImport([{ sku_code: "LAST-SKU", on_hand_units: "20" }], () => {})}>Run test import</button></div> : null }));

import { InventoryPage } from "@/pages/Inventory";
import { useAuthStore } from "@/stores/auth";

const stock = (location: string, units: number) => ({
  sku_id: "sku-1", sku_code: "SHIRT-M", location, on_hand_units: units, inbound_units: 0,
  reserved_units: 0, available_units: units, as_of: "2026-10-26T00:00:00Z", source: "csv",
});
const payload = () => ({
  total_skus: 260, total_positions: 520, offset: 0, limit: 25,
  totals: { available_units: 3000, inbound_units: 20 }, locations: ["Hyderabad", "Warangal"],
  skus: [{ sku_id: "sku-1", sku_code: "SHIRT-M", product_name: "Linen shirt" }],
  levels: [stock("Hyderabad", 4), stock("Warangal", 40)],
  coverage: { skus: [{ sku_id: "sku-1", sku_code: "SHIRT-M", lead_time_days: 14, lead_time_assumed: true,
    demand: { basis: "forecast", reason: "Forecast demand", weekly_units: 20, run_id: "run-1" },
    sku_wide: { cover_days: 15.4, status: "healthy", reason: "Pooled coverage" },
    locations: [
      { location: "Hyderabad", cover_days: 2.8, status: "critical", reason: "Location forecast", demand_basis: "forecast" },
      { location: "Warangal", cover_days: null, status: null, reason: "No store-tagged sales" },
    ],
  }] },
});
const renderPage = (client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) => render(
  <QueryClientProvider client={client}>
    <MemoryRouter><InventoryPage /></MemoryRouter>
  </QueryClientProvider>,
);
beforeEach(() => { useAuthStore.setState({ tenantId: "tenant-a" }); api.overview.mockReset(); api.overview.mockResolvedValue(payload()); });

it("shows one SKU row with store attention, not duplicated SKU rows", async () => {
  renderPage();
  expect(await screen.findByText("Linen shirt")).toBeInTheDocument();
  expect(screen.getAllByText("SHIRT-M")).toHaveLength(1);
  expect(screen.getByText("260 SKUs · 520 stock positions")).toBeInTheDocument();
  expect(screen.getByText("1 store needs stock")).toBeInTheDocument();
});

it("labels period-average cover as an estimate rather than a model forecast", async () => {
  const data = payload();
  data.coverage.skus[0].demand.basis = "period_average";
  data.coverage.skus[0].locations[0].demand_basis = "period_average";
  api.overview.mockResolvedValue(data);
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /show stores for shirt-m/i }));
  expect(screen.getByText("Estimated stock cover: 2.8 days")).toBeInTheDocument();
  expect(screen.getByText(/Average-sales estimates are used/)).toBeInTheDocument();
});

it("expands store details with honest shortage guidance and no pooled-as-store cover", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /show stores for shirt-m/i }));
  expect(screen.getByText("Stock lasts 2.8 days")).toBeInTheDocument();
  expect(screen.getByText("Review shortage")).toBeInTheDocument();
  expect(screen.getByText("Store cover unknown")).toBeInTheDocument();
  expect(screen.queryByText(/Stock lasts 15.4 days/)).not.toBeInTheDocument();
  expect(screen.queryByText("No action")).not.toBeInTheDocument();
  expect(screen.getAllByText(/CSV import · as of/)).toHaveLength(2);
  expect(screen.getByText(/Replenishment time assumed: 14 days/)).toBeInTheDocument();
});

it("sends attention filters to the server so results are not limited to the visible page", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Overstock" }));
  await waitFor(() => expect(api.overview).toHaveBeenLastCalledWith(expect.objectContaining({
    attention: "excess",
    offset: 0,
  })));
});

it("searches and filters location on the server, resetting pagination", async () => {
  renderPage();
  await screen.findByText("Linen shirt");
  fireEvent.change(screen.getByRole("searchbox", { name: "Search stock" }), { target: { value: "linen" } });
  await waitFor(() => expect(api.overview).toHaveBeenLastCalledWith(expect.objectContaining({ search: "linen", offset: 0 })));
  fireEvent.change(screen.getByRole("combobox", { name: "Location" }), { target: { value: "Hyderabad" } });
  await waitFor(() => expect(api.overview).toHaveBeenLastCalledWith(expect.objectContaining({ location: "Hyderabad", offset: 0 })));
});

it("shows import onboarding without misleading zero summaries when inventory is empty", async () => {
  api.overview.mockResolvedValue({ ...payload(), total_skus: 0, total_positions: 0, skus: [], levels: [], coverage: { skus: [] } });
  renderPage();
  expect(await screen.findByText("Build your stock picture")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /add products and skus/i })).toHaveAttribute("href", "/workspace/products");
  expect(screen.getByRole("link", { name: "Add sales history" })).toHaveAttribute("href", "/workspace/integrations");
  expect(screen.getByRole("button", { name: "Import stock" })).toBeInTheDocument();
  expect(screen.getByText("Upload on-hand, reserved and arriving quantities.")).toBeInTheDocument();
  expect(screen.queryByText("Available units")).not.toBeInTheDocument();
});

it("does not call an evidenced zero-demand store missing data", async () => {
  const data = payload();
  data.coverage.skus[0].locations[0].status = "healthy";
  data.coverage.skus[0].locations[0].cover_days = null as unknown as number;
  Object.assign(data.coverage.skus[0].locations[0], { location_demand: { weekly_units: 0 }, demand_basis: "forecast" });
  api.overview.mockResolvedValue(data);
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /show stores for shirt-m/i }));
  const hyderabad = screen.getByText("Hyderabad", { selector: "h3" }).closest("section")!;
  expect(within(hyderabad).getByText("No sales expected in this forecast window")).toBeInTheDocument();
  expect(within(hyderabad).queryByText("Missing data")).not.toBeInTheDocument();
});

it("shows store details directly in a location view without a nonfunctional disclosure", async () => {
  renderPage();
  await screen.findByText("Linen shirt");
  fireEvent.change(screen.getByRole("combobox", { name: "Location" }), { target: { value: "Hyderabad" } });
  expect(await screen.findByText("Hyderabad", { selector: "h3" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /show stores for/i })).not.toBeInTheDocument();
  expect(screen.getByText("Linen shirt")).toBeInTheDocument();
});

it("reports unavailable stock honestly instead of claiming the workspace is empty", async () => {
  api.overview.mockRejectedValue(new Error("503"));
  renderPage();
  expect(await screen.findByRole("alert")).toHaveTextContent(/stock could not be loaded/i);
  expect(screen.queryByText("Build your stock picture")).not.toBeInTheDocument();
});

it("refreshes the stock and its coverage together", async () => {
  renderPage();
  await screen.findByText("Linen shirt");
  const before = api.overview.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() => expect(api.overview.mock.calls.length).toBeGreaterThan(before));
});

it("shows a source-specific transfer only on the matching store", async () => {
  const data = payload();
  Object.assign(data.coverage.skus[0].locations[0], { open_transfer: { units: 3, destination: "Warangal" } });
  api.overview.mockResolvedValue(data);
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /show stores for shirt-m/i }));
  const hyderabad = screen.getByText("Hyderabad", { selector: "h3" }).closest("section")!;
  expect(within(hyderabad).getByText("Review transfer of 3 to Warangal")).toBeInTheDocument();
  const warangal = screen.getByText("Warangal", { selector: "h3" }).closest("section")!;
  expect(within(warangal).queryByText(/Review transfer/)).not.toBeInTheDocument();
});

it("shows a saved recommendation only for its exact SKU and destination store", async () => {
  const data = { ...payload(), recommendations: [
    { sku_id: "sku-1", location: "Warangal", headline: "Review Warangal order" },
    { sku_id: "sku-other", location: "Hyderabad", headline: "Another SKU order" },
    { sku_id: "sku-1", location: null, headline: "Pooled order" },
  ] };
  api.overview.mockResolvedValue(data);
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: /show stores for shirt-m/i }));
  const hyderabad = screen.getByText("Hyderabad", { selector: "h3" }).closest("section")!;
  expect(within(hyderabad).getByText("Review shortage")).toBeInTheDocument();
  const warangal = screen.getByText("Warangal", { selector: "h3" }).closest("section")!;
  expect(within(warangal).getByText("Review Warangal order")).toBeInTheDocument();
  expect(screen.queryByText("Another SKU order")).not.toBeInTheDocument();
  expect(screen.queryByText("Pooled order")).not.toBeInTheDocument();
});

it("never reuses stock or placeholder rows across tenants sharing an industry", async () => {
  renderPage();
  await screen.findByText("Linen shirt");
  api.overview.mockImplementation(() => new Promise(() => {}));
  act(() => useAuthStore.setState({ tenantId: "tenant-b" }));
  expect(screen.queryByText("Linen shirt")).not.toBeInTheDocument();
  expect(screen.queryByText("260 SKUs · 520 stock positions")).not.toBeInTheDocument();
  await waitFor(() => expect(api.overview).toHaveBeenCalledTimes(2));
});

it("imports a SKU beyond the first catalogue page and refreshes its coverage", async () => {
  const rows = [{ sku_code: "LAST-SKU", on_hand_units: "20" }];
  api.parseFile.mockResolvedValue({ rows, errors: [] });
  api.validateRows.mockReturnValue({ valid: rows, invalid: [] });
  api.skuList.mockResolvedValueOnce(Array.from({ length: 200 }, (_, i) => ({ id: `sku-${i}`, sku_code: `SKU-${i}` })))
    .mockResolvedValueOnce([{ id: "last-sku-id", sku_code: "LAST-SKU" }]);
  api.upsert.mockResolvedValue({ upserted: 1 });
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Import stock" }));
  fireEvent.click(screen.getByRole("button", { name: "Parse test file" }));
  await waitFor(() => expect(api.validateRows).toHaveBeenCalledWith(rows, { "LAST-SKU": "last-sku-id" }));
  expect(api.skuList).toHaveBeenLastCalledWith({ offset: 200, limit: 200, active_only: false });
  const before = api.overview.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Run test import" }));
  await waitFor(() => expect(api.upsert).toHaveBeenCalledWith([expect.objectContaining({ sku_id: "last-sku-id", on_hand_units: 20 })]));
  await waitFor(() => expect(api.overview.mock.calls.length).toBeGreaterThan(before));
});

it("closes a parsed stock import when the tenant changes", async () => {
  api.validateRows.mockClear();
  api.parseFile.mockResolvedValue({ rows: [{ sku_code: "LAST-SKU", on_hand_units: "20" }], errors: [] });
  api.skuList.mockResolvedValue([{ id: "tenant-a-sku", sku_code: "LAST-SKU" }]);
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Import stock" }));
  fireEvent.click(screen.getByRole("button", { name: "Parse test file" }));
  await waitFor(() => expect(api.validateRows).toHaveBeenCalled());
  act(() => useAuthStore.setState({ tenantId: "tenant-b" }));
  await screen.findByText("Linen shirt");
  expect(screen.queryByRole("button", { name: "Run test import" })).not.toBeInTheDocument();
});

it("uses the paired theme foreground for filled controls in dark mode", async () => {
  document.documentElement.classList.add("dark");
  try {
    renderPage();
    // The dark theme's pale accent requires its dark --accent-fg, not fixed white.
    expect(await screen.findByRole("button", { name: "Import stock" })).toHaveClass("!text-accent-fg");
    expect(screen.getByRole("button", { name: "All" })).toHaveClass("!text-accent-fg");
    fireEvent.click(screen.getByRole("button", { name: "Overstock" }));
    expect(screen.getByRole("button", { name: "Overstock" })).toHaveClass("!text-accent-fg");
    expect(screen.getByRole("button", { name: "All" })).not.toHaveClass("!text-accent-fg");
  } finally {
    document.documentElement.classList.remove("dark");
  }
});
