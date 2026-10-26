import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadPanel } from "./Integrations";

const api = vi.hoisted(() => ({ analyze: vi.fn(), upload: vi.fn(), success: vi.fn() }));
vi.mock("@/api/integrations", () => ({ integrationsApi: api }));
vi.mock("react-hot-toast", () => ({ default: { success: api.success, error: vi.fn() } }));

/**
 * Source-level assertion. Integrations is a 950-line page of provider panels
 * behind a modal and a live catalog query; what matters here is a single fact
 * that is plainly visible in the source — it no longer offers, or sends, a
 * target industry. The server refuses a mismatched one either way.
 */
const source = readFileSync("src/pages/Integrations.tsx", "utf8");

describe("integrations", () => {
  it("sends period identity when totals are selected and reports unchanged rows", async () => {
    api.analyze.mockResolvedValue({ headers: ["sku", "qty", "date"], sample_rows: [],
      suggested_mapping: { sku: "sku", quantity: "qty", timestamp: "date" } });
    api.upload.mockResolvedValue({ kind: "sales", rows_inserted: 0, rows_unchanged: 459,
      rows_updated: 0, rows_skipped: 0, identity_mode: "period", warnings: [] });
    const done = vi.fn();
    const client = new QueryClient();
    client.setQueryData(["dashboard-forecast", "fashion"], { rows: [{ p50: 10 }] });
    client.setQueryData(["dashboard-history", "fashion"], { series: [] });
    const { container } = render(<QueryClientProvider client={client}><UploadPanel onDone={done} /></QueryClientProvider>);
    const user = userEvent.setup();
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, new File(["sku,qty,date"], "sales.csv"));
    await user.click(await screen.findByLabelText(/Daily or weekly totals/));
    await user.click(screen.getByRole("button", { name: /import/i }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(api.upload).toHaveBeenCalledWith(expect.any(File), "sales", expect.any(Object), { identity: "period", currency: undefined });
    expect(api.success).toHaveBeenCalledWith("0 new · 459 already imported · 0 corrected");
    expect(client.getQueryState(["dashboard-forecast", "fashion"])?.isInvalidated).toBe(true);
    expect(client.getQueryState(["dashboard-history", "fashion"])?.isInvalidated).toBe(true);
  });

  it("never sends a target industry", () => {
    expect(source).not.toMatch(/target_industry/);
  });

  it("offers no industry selector", () => {
    expect(source).not.toMatch(/Target industry/i);
    expect(source).not.toMatch(/setIndustry/);
  });
});
