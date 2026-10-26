import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { StepData } from "./StepData";

const api = vi.hoisted(() => ({ analyze: vi.fn(), upload: vi.fn(), success: vi.fn() }));
vi.mock("@/api/integrations", () => ({ integrationsApi: api }));
vi.mock("react-hot-toast", () => ({ default: { success: api.success, error: vi.fn() } }));
vi.mock("@/components/ui/FileDropzone", () => ({
  FileDropzone: ({ onFile }: { onFile: (f: File) => void }) =>
    <button onClick={() => onFile(new File(["sku,quantity,date"], "sales.csv"))}>Choose file</button>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  api.analyze.mockResolvedValue({ headers: ["sku", "quantity", "date"],
    suggested_mapping: { sku: "sku", quantity: "quantity", timestamp: "date" } });
  api.upload.mockResolvedValue({ kind: "sales", rows_total: 459, rows_imported: 0,
    rows_inserted: 0, rows_updated: 0, rows_unchanged: 459, rows_skipped: 0,
    identity_mode: "period", errors: [], warnings: [], sales_rows: 0 });
});

it("offers period totals during onboarding and reports a replay honestly", async () => {
  render(<StepData thisStep="data" save={vi.fn()} />);
  const user = userEvent.setup();
  const sales = screen.getByText("Sales history").closest("div.rounded-2xl") as HTMLElement;
  await user.click(within(sales).getByText("Choose file"));
  await user.click(await within(sales).findByLabelText("Weekly/daily totals (corrections replace)"));
  await user.click(within(sales).getByRole("button", { name: "Import" }));
  expect(await screen.findByText("0 new · 459 already imported · 0 corrected")).toBeInTheDocument();
  expect(api.upload).toHaveBeenCalledWith(expect.any(File), "sales", expect.any(Object), { identity: "period" });
  expect(api.success).toHaveBeenCalledWith("0 new · 459 already imported · 0 corrected");
});
