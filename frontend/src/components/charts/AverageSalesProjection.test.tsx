import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
vi.mock("@/api/periodProjection", () => ({ periodProjectionApi: { get } }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
import { AverageSalesProjection } from "./AverageSalesProjection";

const data = () => ({ status: "available", basis: "period_average", catalogue_skus: 100, matched_skus: 11,
  eligible_skus: 10, missing_skus: 89, unsupported_skus: 1, filtered_skus: 30, offset: 0, limit: 25,
  projected_units: 280, projection_start: "2026-10-27", projection_end: "2027-01-18", horizon_weeks: 12,
  source_periods: [{ start: "2026-01-01", end: "2026-10-25", days: 298, source: "client.xlsx" }],
  limitations: ["No confidence interval is available."],
  rows: [{ sku_id: "sku-1", sku_code: "CLIENT-1", product_name: "Client kurti", weekly_units: 7,
    projected_units: 84, available_units: 10, estimated_cover_days: 10, reported_units: 298, days: 298,
    locations: [{ location: "alwal", weekly_units: 3.5, projected_units: 42, available_units: 10, estimated_cover_days: 20 },
      { location: "unmatched store", weekly_units: null, projected_units: null, available_units: 1, estimated_cover_days: null }] }],
});
const renderPanel = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AverageSalesProjection /></QueryClientProvider>);
beforeEach(() => { get.mockReset(); get.mockResolvedValue(data()); });

it("labels the constant projection and incomplete coverage without invented confidence", async () => {
  renderPanel();
  expect(await screen.findByRole("heading", { name: "Average-sales projection" })).toBeInTheDocument();
  expect(await screen.findByText(/10 of 100/)).toBeInTheDocument();
  expect(screen.getByText(/89.*no matching.*1.*unsupported/i)).toBeInTheDocument();
  expect(screen.getAllByText(/298 days/).length).toBeGreaterThan(0);
  expect(screen.getByText("No confidence interval is available.")).toBeInTheDocument();
  expect(screen.queryByText(/P90|P10|Chronos zero-shot/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Store estimates"));
  expect(screen.getByText("unmatched store")).toBeInTheDocument();
  expect(screen.getAllByText(/Unavailable/).length).toBeGreaterThan(0);
});

it("changes horizon and search and pages on the server", async () => {
  renderPanel();
  await screen.findByText("Client kurti");
  fireEvent.click(screen.getByRole("button", { name: "Next projection page" }));
  await waitFor(() => expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })));
  fireEvent.change(screen.getByRole("searchbox", { name: "Search projected SKUs" }), { target: { value: "CLIENT" } });
  await waitFor(() => expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0, search: "CLIENT" })));
  fireEvent.change(screen.getByRole("combobox", { name: "Projection horizon" }), { target: { value: "4" } });
  await waitFor(() => expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ horizon_weeks: 4, offset: 0 })));
});

it("reports a failed request without showing a zero projection", async () => {
  get.mockRejectedValue(new Error("offline"));
  renderPanel();
  expect(await screen.findByRole("alert")).toHaveTextContent("Projection could not be loaded");
  expect(screen.queryByText("0 projected units")).not.toBeInTheDocument();
});
