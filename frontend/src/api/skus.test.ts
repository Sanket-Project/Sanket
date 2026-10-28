import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.hoisted(() => vi.fn());
vi.mock("@/api/client", () => ({ apiClient: { post } }));

import { skusApi } from "@/api/skus";

const ok = (created: number) => ({ data: { created, skipped: 0, failed: 0, errors: [] } });
const sentRows = (call: number) => post.mock.calls[call][1].rows;

beforeEach(() => {
  post.mockReset();
});

describe("skusApi.bulkCreate", () => {
  it("sends a 1,200-row file as three bulk requests instead of one per SKU", async () => {
    post.mockImplementation((_url: string, body: { rows: unknown[] }) => Promise.resolve(ok(body.rows.length)));
    const rows = Array.from({ length: 1200 }, (_, i) => ({ sku_code: `SKU-${i}`, product_external_id: "P-1" }));
    const progress: number[] = [];

    const result = await skusApi.bulkCreate(rows, (done) => progress.push(done));

    expect(post.mock.calls.map(([url]) => url)).toEqual(["/skus/bulk", "/skus/bulk", "/skus/bulk"]);
    expect([0, 1, 2].map((c) => sentRows(c).length)).toEqual([500, 500, 200]);
    expect(progress).toEqual([500, 1000, 1200]);
    expect(result).toEqual({ created: 1200, skipped: 0, failed: 0, errors: [] });
  });

  it("reads a catalogue export's own column names", async () => {
    post.mockResolvedValue(ok(2));

    await skusApi.bulkCreate(
      [
        {
          sku_code: "SWF-LEH0001-NVY-FS", product_id: "PRD-1001", selling_price_inr: "11849",
          cost_price_inr: "7650", barcode_ean13: "8907412100019", color: "Navy Blue",
          size: "Free Size", mrp_inr: "12499", status: "Inactive",
        },
        { sku_code: "SWF-GRL0001-MGT-1Y", product_id: "PRD-1002", status: "Draft" },
      ],
      () => {},
    );

    expect(sentRows(0)).toEqual([
      {
        product: "PRD-1001", sku_code: "SWF-LEH0001-NVY-FS", unit_price: 11849, unit_cost: 7650,
        gtin: "8907412100019", attributes: { color: "Navy Blue" }, is_active: false,
        moq: 1, safety_stock: 0, reorder_point: 0,
      },
      {
        product: "PRD-1002", sku_code: "SWF-GRL0001-MGT-1Y", is_active: false,
        moq: 1, safety_stock: 0, reorder_point: 0,
      },
    ]);
  });

  it("still reads the template's column names", async () => {
    post.mockResolvedValue(ok(1));

    await skusApi.bulkCreate(
      [{ product_external_id: "WGT-001", sku_code: "WGT-001-BLK", unit_price: "24.99", unit_cost: "12.50",
        currency: "usd", gtin: "123", lead_time: "14", warehouse_inventory: "150" }],
      () => {},
    );

    expect(sentRows(0)).toEqual([
      {
        product: "WGT-001", sku_code: "WGT-001-BLK", unit_price: 24.99, unit_cost: 12.5, currency: "USD",
        gtin: "123", lead_time_days: 14, attributes: { warehouse_inventory: 150, lead_time: 14 },
        is_active: true, moq: 1, safety_stock: 0, reorder_point: 0,
      },
    ]);
  });

  it("pins each server-reported failure to its own row", async () => {
    post.mockResolvedValue({
      data: { created: 1, skipped: 1, failed: 1, errors: [{ index: 2, sku_code: "C", reason: "No product with code or id 'PRD-1185'" }] },
    });
    const rows = [
      { sku_code: "A", product_id: "PRD-1" },
      { sku_code: "B", product_id: "PRD-1" },
      { sku_code: "C", product_id: "PRD-1185" },
    ];

    const result = await skusApi.bulkCreate(rows, () => {});

    expect(result).toEqual({
      created: 1, skipped: 1, failed: 1,
      errors: [{ row: rows[2], reason: "No product with code or id 'PRD-1185'" }],
    });
  });

  it("fails only the batch whose request failed, with the server's reason", async () => {
    post
      .mockRejectedValueOnce({ response: { status: 429, data: { detail: "Rate limit exceeded" } } })
      .mockResolvedValueOnce(ok(1));
    const rows = Array.from({ length: 501 }, (_, i) => ({ sku_code: `S-${i}`, product_id: "P" }));

    const result = await skusApi.bulkCreate(rows, () => {});

    expect(result.created).toBe(1);
    expect(result.failed).toBe(500);
    expect(result.errors).toHaveLength(500);
    expect(result.errors[0]).toEqual({ row: rows[0], reason: "Rate limit exceeded" });
  });
});
