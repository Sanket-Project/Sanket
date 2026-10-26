import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CoverageResponse, CoverageStatus, InventoryLevel, LocationCoverage } from "@/api/inventory";

const api = vi.hoisted(() => ({ levels: vi.fn(), coverage: vi.fn(), upsert: vi.fn() }));

vi.mock("@/api/inventory", () => ({
  inventoryApi: { levels: api.levels, coverage: api.coverage, upsert: api.upsert },
  validateInventoryRows: vi.fn(),
  downloadInventoryTemplate: vi.fn(),
}));
vi.mock("@/api/skus", () => ({ skusApi: { list: vi.fn().mockResolvedValue([]) } }));
vi.mock("@/api/decisions", () => ({ decisionsApi: { list: vi.fn().mockResolvedValue({ decisions: [] }) } }));
vi.mock("@/api/export", () => ({ exportApi: { inventoryCsv: vi.fn() } }));
// The real modal is a multi-step file flow; this stand-in drives onImport directly.
vi.mock("@/components/ui/ImportModal", () => ({
  ImportModal: ({ onImport }: { onImport: (rows: unknown[], p: () => void) => Promise<unknown> }) => (
    <button type="button" onClick={() => {
      api.upsert.mockResolvedValue({ upserted: 1 });
      void onImport([{ sku_code: "PALAZZO-XL", on_hand_units: "20" }], () => {});
    }}>Run test import</button>
  ),
}));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { InventoryPage } from "@/pages/Inventory";

const level = (location: string, units: number): InventoryLevel => ({
  sku_id: "sku-1", sku_code: "PALAZZO-XL", location, on_hand_units: units, inbound_units: 0,
  reserved_units: 0, available_units: units, as_of: "2026-10-25T00:00:00Z", source: "upload",
});

const coverage = (over: Partial<CoverageResponse["skus"][number]>): CoverageResponse => ({
  industry: "fashion",
  as_of: "2026-10-26T09:00:00Z",
  calendar: "W-MON-UTC",
  policy: { forecast_max_age_days: 14, forecast_weeks: 4, trailing_weeks: 8, min_weeks: 4,
    stale_stock_days: 30, low_multiplier: 1.5, transfer_suggestions: false },
  skus: [{
    sku_id: "sku-1", sku_code: "PALAZZO-XL", lead_time_days: 14, lead_time_assumed: false,
    demand: { basis: "trailing_actuals", weekly_units: 25, run_id: null, reason: "" },
    sku_wide: { available_units: 220, inbound_units: 0, cover_days: 61.6, status: "healthy", reason: "" },
    locations: [],
    ...over,
  }],
});

const loc = (
  location: string, units: number, cover: number | null, status: CoverageStatus | null, reason = "",
): LocationCoverage => ({
  location, available_units: units, on_hand_units: units, inbound_units: 0,
  as_of: "2026-10-25T00:00:00Z", stock_stale: false,
  location_demand: { weekly_units: cover == null ? null : 20, weeks_observed: 8, basis: cover == null ? null : "location_sales" as const },
  cover_days: cover, status, reason,
});

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <InventoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("Inventory coverage (audit F09)", () => {
  beforeEach(() => {
    api.levels.mockResolvedValue({ industry: "fashion", count: 2, levels: [level("Boduppal", 30), level("Alwal", 190)] });
  });

  it("calls stock with no demand basis unknown, never healthy", async () => {
    api.coverage.mockResolvedValue(coverage({
      demand: { basis: null, weekly_units: null, run_id: null, reason: "No demand basis: only 2 of the last 8 weeks have sales." },
      sku_wide: { available_units: 220, inbound_units: 0, cover_days: null, status: "unknown",
        reason: "No demand basis: only 2 of the last 8 weeks have sales." },
      locations: [loc("Boduppal", 30, null, null, "pooled"), loc("Alwal", 190, null, null, "pooled")],
    }));

    renderPage();

    await screen.findAllByText("Unknown");
    const statusRows = screen.getAllByRole("row").slice(1);
    expect(statusRows.filter((r) => /Unknown/.test(r.textContent ?? "")).length).toBe(2);
    expect(screen.getAllByText(/No demand basis/).length).toBeGreaterThan(0);
    const rows = screen.getAllByRole("row").slice(1); // skip the header row
    expect(rows.some((r) => /Healthy/.test(r.textContent ?? ""))).toBe(false);
    expect(document.body.textContent).not.toMatch(/above the immediate risk threshold/);
  });

  it("shows store cover only where store sales exist, and labels pooled cover", async () => {
    api.coverage.mockResolvedValue(coverage({
      locations: [
        loc("Boduppal", 30, 10.5, "critical"),
        loc("Alwal", 190, null, null, "Cover is SKU-wide (all locations pooled)"),
      ],
    }));

    renderPage();

    expect(await screen.findByText("Store cover 10.5 days")).toBeInTheDocument();
    expect(screen.getByText("SKU-wide cover 61.6 days (all locations)")).toBeInTheDocument();
    expect(screen.getByText("1 critical · 0 low")).toBeInTheDocument();
  });
});

describe("Inventory remediation (deep audit F8, F9, F14, F16)", () => {
  beforeEach(() => {
    api.levels.mockReset();
    api.coverage.mockReset();
    api.upsert.mockReset();
    api.levels.mockResolvedValue({ industry: "fashion", count: 1, levels: [level("Boduppal", 30)] });
  });

  it("says stock could not be loaded instead of claiming there is none", async () => {
    api.levels.mockRejectedValue(new Error("503"));
    api.coverage.mockResolvedValue(coverage({}));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/stock could not be loaded/i);
    expect(screen.queryByText("No stock data yet")).not.toBeInTheDocument();
  });

  it("says cover is unavailable when coverage fails, never Unknown/No action as if computed", async () => {
    api.coverage.mockRejectedValue(new Error("503"));

    renderPage();

    expect(await screen.findByText(/cover could not be loaded/i)).toBeInTheDocument();
    expect(screen.queryByText("No action")).not.toBeInTheDocument();
  });

  it("refetches coverage when the user refreshes stock", async () => {
    api.coverage.mockResolvedValue(coverage({}));
    renderPage();
    await screen.findByText(/SKU-wide cover 61.6 days/);
    const before = api.coverage.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => expect(api.coverage.mock.calls.length).toBeGreaterThan(before));
  });

  it("shows the new cover immediately after an import changes stock", async () => {
    api.coverage.mockResolvedValueOnce(coverage({}));
    renderPage();
    await screen.findByText(/SKU-wide cover 61.6 days/);
    api.coverage.mockResolvedValue(coverage({
      sku_wide: { available_units: 20, inbound_units: 0, cover_days: 5.6, status: "critical", reason: "" },
    }));

    fireEvent.click(screen.getByRole("button", { name: "Run test import" }));

    expect(await screen.findByText(/SKU-wide cover 5.6 days/)).toBeInTheDocument();
  });

  it("labels provenance explicitly instead of 'Real'", async () => {
    api.levels.mockResolvedValue({ industry: "fashion", count: 1, levels: [{ ...level("Boduppal", 30), source: "csv" }] });
    api.coverage.mockResolvedValue(coverage({}));

    renderPage();

    expect(await screen.findByText(/CSV import · as of 25 Oct 2026/)).toBeInTheDocument();
    expect(screen.queryByText("Real")).not.toBeInTheDocument();
  });

  it("flags an assumed lead time beside the cover", async () => {
    api.coverage.mockResolvedValue(coverage({ lead_time_assumed: true }));

    renderPage();

    expect(await screen.findByText("Lead time assumed (14-day default)")).toBeInTheDocument();
  });

  it("calls long cover excess and suggests the excess-stock next action", async () => {
    api.coverage.mockResolvedValue(coverage({
      sku_wide: { available_units: 1000, inbound_units: 0, cover_days: 466.7, status: "excess",
        reason: "", next_action: "Pause reorders, review inbound stock, and consider a transfer or markdown." },
    }));

    renderPage();

    expect(await screen.findAllByText("Excess")).not.toHaveLength(0);
    expect(screen.getByText(/Pause reorders, review inbound stock/)).toBeInTheDocument();
  });
});
