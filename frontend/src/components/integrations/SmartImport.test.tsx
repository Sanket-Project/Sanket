import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { SmartImport } from "./SmartImport";
import { useAuthStore } from "@/stores/auth";

const api = vi.hoisted(() => ({ planImport: vi.fn(), previewPlan: vi.fn(), confirmPlan: vi.fn() }));
vi.mock("@/api/integrations", () => ({ integrationsApi: api }));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));

const evaluation = {
  preview: { source_rows: 3, excluded_rows: 1, output_rows: 2, items: 2, locations: 2, conflicts: 0,
    before: [{ c1: "ALWAL", c2: "S1" }], after: [{ sku: "SUKANYA-49159-WHITE-L", available: 2 }] },
  exclusions: [{ row: 5, reason: "summary_row" }],
  size_codes: [{ code: "0L", count: 2594, suggestion: null }, { code: "XL", count: 494, suggestion: "XL" }],
  missing: { products: [], inventory: [] },
};
const stock = {
  file_index: 0, filename: "stock.csv", plan_token: "tok-1", plan_source: "rules", ai_state: "disabled",
  table: { sheet: "CSV", header_start: 1, header_end: 1, rows_total: 4 },
  columns: [{ id: "c1", label: "Company Name", kind: "text", derived: false },
    { id: "c2", label: "Stock No", kind: "text", derived: false },
    { id: "x_sku", label: "Variant SKU (brand-style-colour-size)", kind: "text", derived: true }],
  provenance: { c1: "alias", c2: "alias" },
  decision: { destinations: ["products", "inventory"], mapping: { sku: "x_sku", warehouse: "c1", style: "c2" },
    transforms: { parse_variant: true, group_pieces: true }, size_map: {}, period: null, currency: null },
  unusable_reason: null, warnings: [], ...evaluation,
};
const dsr = {
  ...stock, file_index: 1, filename: "sales.xlsx", plan_token: "tok-2",
  decision: { ...stock.decision, destinations: [], mapping: {} }, unusable_reason: "no_item_column",
  missing: {},
};

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ role: "owner" } as never);
  api.planImport.mockResolvedValue({ files: [stock, dsr, { file_index: 2, filename: "bad.xlsx", error: "Invalid Excel workbook" }] });
  api.confirmPlan.mockResolvedValue({ destinations: { products: { skus_created: 2 }, inventory: { inventory_rows: 2 } }, rows_excluded: 1 });
  api.previewPlan.mockResolvedValue({ decision: stock.decision, ...evaluation });
});

async function planThreeFiles() {
  const { container } = render(<SmartImport />);
  const files = [new File(["a"], "stock.csv"), new File(["b"], "sales.xlsx"), new File(["c"], "bad.xlsx")];
  await userEvent.upload(container.querySelector('input[type="file"]')!, files);
  await screen.findByRole("region", { name: "stock.csv" });
  return files;
}

it("plans several files and shows one card per file", async () => {
  const files = await planThreeFiles();
  expect(api.planImport).toHaveBeenCalledWith(files);
  expect(screen.getByRole("region", { name: "sales.xlsx" })).toHaveTextContent(/No column identifies an item/);
  expect(screen.getByRole("region", { name: "bad.xlsx" })).toHaveTextContent("Invalid Excel workbook");
  const card = screen.getByRole("region", { name: "stock.csv" });
  expect(card).toHaveTextContent(/3 rows → 2 SKUs in 2 rows across 2 locations/);
  expect(within(card).getByText("0L")).toBeInTheDocument();
});

it("imports a file with the user's edits", async () => {
  const files = await planThreeFiles();
  const card = screen.getByRole("region", { name: "stock.csv" });
  await userEvent.selectOptions(within(card).getByLabelText("Size for code 0L"), "L");
  await userEvent.click(within(card).getByRole("button", { name: "Import this file" }));
  await waitFor(() => expect(api.confirmPlan).toHaveBeenCalled());
  expect(api.confirmPlan).toHaveBeenCalledWith(files[0], "tok-1", expect.objectContaining({
    destinations: ["products", "inventory"], size_map: { "0L": "L" },
  }));
  expect(await within(card).findByText(/Imported/)).toBeInTheDocument();
});

it("refreshes the preview after a transform is switched off", async () => {
  await planThreeFiles();
  const card = screen.getByRole("region", { name: "stock.csv" });
  await userEvent.click(within(card).getByLabelText(/Group pieces/));
  await userEvent.click(within(card).getByRole("button", { name: "Update preview" }));
  await waitFor(() => expect(api.previewPlan).toHaveBeenCalled());
  const sent = api.previewPlan.mock.calls[0][2];
  expect(sent.transforms).toEqual({ parse_variant: true, group_pieces: false });
});

it("does not offer import on unusable files or to viewers", async () => {
  useAuthStore.setState({ role: "viewer" } as never);
  await planThreeFiles();
  expect(within(screen.getByRole("region", { name: "sales.xlsx" })).queryByRole("button", { name: "Import this file" })).toBeNull();
  expect(within(screen.getByRole("region", { name: "stock.csv" })).getByRole("button", { name: "Import this file" })).toBeDisabled();
});

it("shows value problems and blocks the import", async () => {
  api.planImport.mockResolvedValue({ files: [{ ...stock, problems: ["SKU BHAKTI-1-L: 'n/a' is not a number"] }] });
  const { container } = render(<SmartImport />);
  await userEvent.upload(container.querySelector('input[type="file"]')!, [new File(["a"], "stock.csv")]);
  const card = await screen.findByRole("region", { name: "stock.csv" });
  expect(card).toHaveTextContent("SKU BHAKTI-1-L: 'n/a' is not a number");
  expect(within(card).getByRole("button", { name: "Import this file" })).toBeDisabled();
});
