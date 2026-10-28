import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ company: vi.fn(), catalogue: vi.fn(), companyRefresh: vi.fn() }));
const auth = vi.hoisted(() => ({ tenantId: "tenant-1" }));
vi.mock("@/api/trends", () => ({ trendsApi: api }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
vi.mock("@/stores/auth", () => ({ useAuthStore: (selector: (state: typeof auth) => unknown) => selector(auth) }));
import { TrendAnalysisPage } from "./TrendAnalysis";

const result = () => ({
  catalogue: { product_count: 1, sku_count: 2 },
  period: { days: 28, start: "2026-09-29", end: "2026-10-26", previous_start: "2026-09-01" },
  sales: { status: "available", current_units: 60, previous_units: 40, change_pct: 50, observations: 20, as_of: "2026-10-26",
    series: [{ date: "2026-10-19", units: 20 }, { date: "2026-10-26", units: 40 }],
    leaders: [{ sku_id: "sku-1", sku_code: "KURTA-BLUE-M", product_name: "Cotton kurta", current_units: 60, previous_units: 40, change_pct: 50 }] },
  external: { status: "available", as_of: "2026-10-26T08:00:00Z", items: [{ id: "signal-1", term: "cotton kurta", source: "google_trends", captured_at: "2026-10-26T08:00:00Z", relative_interest: 72, region: "Telangana", state: "Telangana", district: null, city: null, geography_level: "state", matched_products: ["Cotton kurta"] }] },
});

const renderPage = (client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) => render(<QueryClientProvider client={client}>
  <MemoryRouter><TrendAnalysisPage /></MemoryRouter>
</QueryClientProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  auth.tenantId = "tenant-1";
  api.company.mockResolvedValue(result());
  api.companyRefresh.mockResolvedValue({ status: "queued" });
  api.catalogue.mockImplementation(({ kind }: { kind: string }) => Promise.resolve({ items: [{ id: kind === "product" ? "product-1" : "sku-1", label: kind === "product" ? "Cotton kurta" : "KURTA-BLUE-M", kind, product_id: "product-1", product_name: "Cotton kurta", sku_code: kind === "sku" ? "KURTA-BLUE-M" : null, category: "Kurtas" }], total: 1, limit: 30, offset: 0 }));
});

describe("Company Trend Analysis", () => {
  it("keeps company sales distinct from catalogue-matched relative external interest", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Company sales" })).toBeInTheDocument();
    expect(screen.getByText("KURTA-BLUE-M")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "External market interest" })).toBeInTheDocument();
    expect(screen.getByText("72 / 100")).toBeInTheDocument();
    expect(screen.getByText(/relative search interest/i)).toBeInTheDocument();
    expect(screen.getByText(/Latest sale in selection:/i)).toHaveTextContent("26 Oct 2026");
    expect(screen.queryByText(/Printed T-Shirts|Sneakers|Demand strongly heating/)).not.toBeInTheDocument();
  });

  it("shows an import prompt and no industry scores when the catalogue is empty", async () => {
    api.company.mockResolvedValue({ ...result(), catalogue: { product_count: 0, sku_count: 0 }, sales: { ...result().sales, status: "no_history", current_units: null, previous_units: null, change_pct: null, series: [], leaders: [] }, external: { status: "no_matches", as_of: null, items: [] } });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Start with your company catalogue" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add products and SKUs" })).toHaveAttribute("href", "/workspace/products");
    expect(screen.queryByText("72 / 100")).not.toBeInTheDocument();
  });

  it("offers Hyderabad and all Telangana districts without inventing district interest", async () => {
    const user = userEvent.setup();
    api.company.mockImplementation((params) => Promise.resolve(params?.district ? { ...result(), sales: { ...result().sales, status: "unmapped_geography", current_units: null, previous_units: null, change_pct: null, series: [], leaders: [] }, external: { status: "no_matches", as_of: null, items: [] } } : result()));
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Regional insights" }));
    await user.click(screen.getByRole("combobox", { name: "State" }));
    await user.click(screen.getByRole("option", { name: "Telangana" }));
    await user.click(screen.getByRole("combobox", { name: "District" }));
    expect(within(screen.getByRole("listbox")).getAllByRole("option")).toHaveLength(34);
    await user.click(screen.getByRole("option", { name: "Hyderabad" }));
    await waitFor(() => expect(api.company).toHaveBeenLastCalledWith(expect.objectContaining({ state: "Telangana", district: "Hyderabad" })));
    expect(await screen.findByText("No external data for this district")).toBeInTheDocument();
    expect(screen.getByText(/explicit state and district mapping/i)).toBeInTheDocument();
    expect(screen.queryByText("72 / 100")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "State" }));
    await user.click(screen.getByRole("option", { name: "Karnataka" }));
    expect(screen.getByRole("combobox", { name: "District" })).toHaveTextContent("All districts");
  });

  it("searches uploaded catalogue options remotely and requests the selected SKU", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("combobox", { name: "SKU" }));
    await user.type(screen.getByRole("searchbox", { name: "Search SKU" }), "KURTA");
    await waitFor(() => expect(api.catalogue).toHaveBeenCalledWith(expect.objectContaining({ kind: "sku", q: "KURTA", limit: 30 })));
    await user.click(await screen.findByRole("option", { name: /KURTA-BLUE-M/ }));
    await waitFor(() => expect(api.company).toHaveBeenLastCalledWith(expect.objectContaining({ sku_id: "sku-1" })));
  });

  it("reports a service error without substituting industry data", async () => {
    api.company.mockRejectedValue(new Error("offline"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Company trends could not be loaded");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("Company sales")).not.toBeInTheDocument();
  });

  it("spaces sales observations by elapsed time and labels the selected historical window", async () => {
    api.company.mockResolvedValue({ ...result(), sales: { ...result().sales, series: [{ date: "2026-10-01", units: 10 }, { date: "2026-10-02", units: 20 }, { date: "2026-10-26", units: 30 }] } });
    renderPage();
    const chart = await screen.findByRole("img", { name: /Sales history/ });
    const secondX = Number(chart.querySelector("polyline")?.getAttribute("points")?.split(" ")[1].split(",")[0]);
    expect(secondX).toBeCloseTo(12 + 616 / 25);
    expect(screen.getByRole("combobox", { name: "Period" })).toHaveTextContent("28-day window");
    expect(screen.getByText("Selected 28 days · units")).toBeInTheDocument();
  });

  it("distinguishes the comparison window from the latest sale within a region", async () => {
    api.company.mockResolvedValue({ ...result(), sales: { ...result().sales, as_of: "2026-10-19T00:00:00Z" } });
    renderPage();
    expect(await screen.findByText(/Latest sale in selection: 19 Oct 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Comparison window ends: 26 Oct 2026/)).toBeInTheDocument();
  });

  it("queues market collection explicitly, then refreshes the saved company evidence", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Refresh market interest" }));
    await waitFor(() => expect(api.companyRefresh).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("status")).toHaveTextContent("Market refresh queued");
    await waitFor(() => expect(api.company.mock.calls.length).toBeGreaterThan(1));
  });

  it("does not reuse another tenant's cached company trends or catalogue", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderPage(client);
    await screen.findByRole("heading", { name: "Company sales" });
    expect(api.company).toHaveBeenCalledTimes(1);
    auth.tenantId = "tenant-2";
    view.rerender(<QueryClientProvider client={client}><MemoryRouter><TrendAnalysisPage /></MemoryRouter></QueryClientProvider>);
    await waitFor(() => expect(api.company).toHaveBeenCalledTimes(2));
    expect(api.catalogue).toHaveBeenCalledTimes(4);
  });

  it("takes missing sales history to the actual upload page", async () => {
    api.company.mockResolvedValue({ ...result(), sales: { ...result().sales, status: "no_history", current_units: null, previous_units: null, change_pct: null, series: [], leaders: [] } });
    renderPage();
    expect(await screen.findByRole("link", { name: "Manage data imports" })).toHaveAttribute("href", "/workspace/integrations");
  });

  it("clears selected client product names and IDs when the tenant changes", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderPage(client);
    await user.click(await screen.findByRole("combobox", { name: "Product" }));
    await user.click(await screen.findByRole("option", { name: /Cotton kurta/ }));
    expect(screen.getByRole("combobox", { name: "Product" })).toHaveTextContent("Cotton kurta");
    auth.tenantId = "tenant-2";
    view.rerender(<QueryClientProvider client={client}><MemoryRouter><TrendAnalysisPage /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByRole("combobox", { name: "Product" })).toHaveTextContent("All products");
    await waitFor(() => expect(api.company).toHaveBeenLastCalledWith(expect.objectContaining({ product_id: undefined, sku_id: undefined })));
  });
});
