import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ImportUploader } from "./ImportUploader";
import { useAuthStore } from "@/stores/auth";

const api = vi.hoisted(() => ({ analyze: vi.fn(), upload: vi.fn(), v2Preview: vi.fn(), v2Confirm: vi.fn() }));
vi.mock("@/api/integrations", () => ({ integrationsApi: api }));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));

const analysis = {
  analysis_token: "bound-token", fields: ["sku", "quantity", "timestamp", "price"],
  headers: ["SKU", "Qty", "Date"], suggested_mapping: {}, sample_rows: [],
  tables: [{ id: "t1", sheet: "Sales", header_start: 3, header_end: 3, rows_total: 1,
    columns: [{ id: "c1", label: "SKU", display_label: "SKU", kind: "text" },
      { id: "c2", label: "मात्रा", display_label: "मात्रा", kind: "integer" },
      { id: "c3", label: "Date", display_label: "Date", kind: "date" }],
    mapping: { sku: "c1", quantity: "c2", timestamp: "c3" }, mapping_source: "saved",
    confidence: { c1: "high", c2: "medium", c3: "high" }, provenance: { c1: "saved", c2: "ai", c3: "saved" },
    ai_state: "success", sample_rows: [{ c1: "A", c2: 3, c3: "2026-01-01" }],
    exclusions: [], review_rows: [], warnings: [], warning_count: 0, profile_revision: 1 }],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.analyze.mockResolvedValue(analysis);
  api.upload.mockResolvedValue({ rows_inserted: 1, rows_updated: 0, rows_unchanged: 0, errors: [], warnings: [] });
});

function v2File() {
  const source = "schema_version\nretail_v2.0.sales\n";
  const file = new File([source], "sales.csv", { type: "text/csv" });
  Object.defineProperty(file, "slice", { value: () => ({ text: async () => source }) });
  return file;
}

it("confirms V2 without legacy analysis and notifies the parent, including replays", async () => {
  useAuthStore.setState({ role: "admin" });
  api.v2Preview.mockResolvedValue({ schema: "retail_v2.0.sales", row_count: 1, headers: [], errors: [], can_confirm: true, preview_token: "v2-token" });
  api.v2Confirm.mockResolvedValueOnce({ rows: 1, inserted: 1, skipped: 0 })
    .mockResolvedValueOnce({ rows: 1, inserted: 0, skipped: 1 });
  const done = vi.fn();
  const { container } = render(<ImportUploader kind="sales" onImported={done} />);
  const file = v2File();
  await userEvent.upload(container.querySelector('input[type="file"]')!, file);
  await screen.findByLabelText("V2 preview");
  await userEvent.click(screen.getByRole("button", { name: "Import" }));
  await waitFor(() => expect(api.v2Confirm).toHaveBeenCalledWith(file, "v2-token"));
  expect(done).toHaveBeenCalledWith(expect.objectContaining({ rows_inserted: 1, sales_rows: 1, rows_unchanged: 0 }));
  await userEvent.click(screen.getByRole("button", { name: "Re-import" }));
  await waitFor(() => expect(done).toHaveBeenLastCalledWith(expect.objectContaining({ rows_inserted: 0, rows_unchanged: 1 })));
  expect(api.analyze).not.toHaveBeenCalled();
  expect(api.upload).not.toHaveBeenCalled();
});

it.each(["invalid", "viewer", "failure"])("handles V2 %s without notifying completion", async (scenario) => {
  const priorRole = useAuthStore.getState().role;
  useAuthStore.setState({ role: scenario === "viewer" ? "viewer" : "admin" });
  api.v2Preview.mockResolvedValue({ schema: "retail_v2.0.sales", row_count: 1, headers: [],
    errors: scenario === "invalid" ? [{ row: 2, code: "UNKNOWN_SKU", message: "Unknown SKU" }] : [],
    can_confirm: scenario !== "invalid", preview_token: "v2-token" });
  api.v2Confirm.mockRejectedValue(new Error("Allocation rejected"));
  const done = vi.fn();
  try {
    const { container } = render(<ImportUploader kind="sales" onImported={done} />);
    await userEvent.upload(container.querySelector('input[type="file"]')!, v2File());
    await screen.findByLabelText("V2 preview");
    const button = screen.getByRole("button", { name: "Import" });
    if (scenario === "failure") {
      await userEvent.click(button);
      expect(await screen.findByRole("alert")).toHaveTextContent("Allocation rejected");
    } else {
      expect(button).toBeDisabled();
      await userEvent.click(button);
      expect(api.v2Confirm).not.toHaveBeenCalled();
    }
    expect(done).not.toHaveBeenCalled();
  } finally { act(() => useAuthStore.setState({ role: priorRole })); }
});

it("shows confidence and saved reuse but requires an explicit import", async () => {
  const done = vi.fn();
  const { container } = render(<ImportUploader kind="sales" onImported={done} />);
  const user = userEvent.setup();
  await user.upload(container.querySelector('input[type="file"]')!, new File(["data"], "a.csv"));
  expect(await screen.findByText(/Saved workspace format/)).toBeInTheDocument();
  expect(screen.getByText(/Model estimate: medium/)).toBeInTheDocument();
  expect(api.upload).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText(/Remember confirmed format/));
  await user.click(screen.getByRole("button", { name: "Import" }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  expect(api.upload).toHaveBeenCalledWith(expect.any(File), "sales", expect.any(Object), expect.objectContaining({
    analysisToken: "bound-token", rememberMapping: true,
    tableSelections: [expect.objectContaining({ id: "t1", mapping: analysis.tables[0].mapping })],
  }));
});

it("allows human mapping edits and blocks duplicate column assignments", async () => {
  const { container } = render(<ImportUploader kind="sales" />);
  await userEvent.upload(container.querySelector('input[type="file"]')!, new File(["data"], "a.csv"));
  await screen.findByText(/Saved workspace format/);
  await userEvent.selectOptions(screen.getByLabelText("Sales: price"), "c2");
  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent(/multiple fields/);
});

it("discards an old analyze response after a file is removed", async () => {
  let resolve: (v: typeof analysis) => void = () => {};
  api.analyze.mockReturnValue(new Promise((r) => { resolve = r; }));
  const { container } = render(<ImportUploader kind="sales" />);
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(["data"], "old.csv")] } });
  await userEvent.click(screen.getByRole("button", { name: "Remove file" }));
  await act(async () => resolve(analysis));
  expect(screen.queryByText(/Saved workspace format/)).not.toBeInTheDocument();
  expect(api.upload).not.toHaveBeenCalled();
});

it("announces unavailable AI while keeping the confirmed manual mapping usable", async () => {
  api.analyze.mockResolvedValue({ ...analysis, tables: [{ ...analysis.tables[0], mapping_source: "alias", ai_state: "unavailable" }] });
  const { container } = render(<ImportUploader kind="sales" />);
  await userEvent.upload(container.querySelector('input[type="file"]')!, new File(["data"], "a.csv"));
  expect(await screen.findByText(/AI suggestions unavailable/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
});

it("previews ambiguous source dates and requires an explicit date order", async () => {
  api.analyze.mockResolvedValue({ ...analysis, tables: [{ ...analysis.tables[0], date_reviews: {
    c3: [{ row: 4, value: "01/02/2026", dmy: "2026-02-01", mdy: "2026-01-02" }],
  }, date_review_counts: { c3: 1 } }] });
  const { container } = render(<ImportUploader kind="sales" />);
  await userEvent.upload(container.querySelector('input[type="file"]')!, new File(["data"], "a.csv"));
  expect(await screen.findByText(/2026-02-01/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText("Sales: date order"), "dmy");
  expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
});

it("preserves a manually selected header when requesting table suggestions", async () => {
  const { container } = render(<ImportUploader kind="sales" />);
  await userEvent.upload(container.querySelector('input[type="file"]')!, new File(["data"], "a.csv"));
  await screen.findByText(/Saved workspace format/);
  await userEvent.click(screen.getByText("Choose sheet and header rows manually"));
  await userEvent.clear(screen.getByLabelText("First header row"));
  await userEvent.type(screen.getByLabelText("First header row"), "111");
  await userEvent.clear(screen.getByLabelText("Last header row"));
  await userEvent.type(screen.getByLabelText("Last header row"), "111");
  await userEvent.click(screen.getByRole("button", { name: "Analyze selected rows" }));
  await screen.findByText(/Saved workspace format/);
  await userEvent.click(screen.getByRole("button", { name: "Suggest mapping for this table" }));
  await waitFor(() => expect(api.analyze).toHaveBeenLastCalledWith(expect.any(File), "sales", { Sales: [111, 111] }, "t1"));
});

it("clears a price-currency choice when the workspace changes", async () => {
  const previousTenant = useAuthStore.getState().tenantId;
  const { container } = render(<ImportUploader kind="sales" />);
  try {
    await userEvent.upload(container.querySelector('input[type="file"]')!, new File(["data"], "a.csv"));
    await screen.findByText(/Saved workspace format/);
    await userEvent.selectOptions(screen.getByLabelText("Currency of prices"), "USD");
    act(() => useAuthStore.setState({ tenantId: "second-workspace" }));
    await userEvent.upload(container.querySelector('input[type="file"]')!, new File(["data"], "b.csv"));
    await screen.findByText(/Saved workspace format/);
    expect(screen.getByLabelText("Currency of prices")).toHaveValue("");
  } finally { act(() => useAuthStore.setState({ tenantId: previousTenant })); }
});
