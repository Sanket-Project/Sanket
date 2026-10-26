import { describe, expect, it, vi } from "vitest";

import type { UploadResult } from "@/api/integrations";
import { describeUploadResult } from "@/utils/uploadSummary";

const post = vi.hoisted(() => vi.fn());
vi.mock("@/api/client", () => ({ apiClient: { post } }));

import { integrationsApi } from "@/api/integrations";

const result = (over: Partial<UploadResult>): UploadResult => ({
  provider: "csv_upload", kind: "sales", rows_total: 532, rows_imported: 0, rows_skipped: 0,
  products_created: 0, skus_created: 0, inventory_rows: 0, sales_rows: 0, errors: [],
  rows_inserted: 0, rows_unchanged: 0, rows_updated: 0, identity_mode: "transaction", warnings: [],
  ...over,
});

describe("describeUploadResult (audit F01)", () => {
  it("says a replayed file added nothing", () => {
    expect(describeUploadResult(result({ rows_unchanged: 532 }))).toBe(
      "0 new · 532 already imported · 0 corrected",
    );
  });

  it("counts corrections and skipped rows", () => {
    expect(describeUploadResult(result({ rows_inserted: 5, rows_updated: 2, rows_skipped: 1 }))).toBe(
      "5 new · 0 already imported · 2 corrected · 1 skipped",
    );
  });

  it("keeps the plain summary for stock and catalogue files", () => {
    expect(describeUploadResult(result({ kind: "inventory", rows_imported: 12, rows_total: 12,
      identity_mode: null }))).toBe("Imported 12 of 12 rows");
  });
});

describe("integrationsApi.upload", () => {
  it("sends how re-uploaded rows are recognised and the file's currency", async () => {
    post.mockResolvedValue({ data: result({}) });
    await integrationsApi.upload(new File(["x"], "s.csv"), "sales", undefined, {
      identity: "period",
      currency: "INR",
    });

    const form = post.mock.calls[0][1] as FormData;
    expect(form.get("identity")).toBe("period");
    expect(form.get("currency")).toBe("INR");
  });
});
