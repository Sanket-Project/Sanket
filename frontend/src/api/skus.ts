import { apiClient } from "@/api/client";
import { cataloguePages } from "@/api/cataloguePagination";
import type { Sku } from "@/types/api";
import type { ParsedRow } from "@/utils/csvImport";
import type { BulkImportResult } from "@/api/products";
import { getErrorMessage } from "@/utils/errors";

export interface SkuCreateBody {
  sku_code: string;
  external_id?: string | null;
  gtin?: string | null;
  description?: string | null;
  unit_cost?: number | null;
  unit_price?: number | null;
  currency?: string;
  lead_time_days?: number | null;
  moq?: number;
  safety_stock?: number;
  reorder_point?: number;
  attributes?: Record<string, unknown>;
}

interface BulkRowResult {
  created: number;
  skipped: number;
  failed: number;
  errors: Array<{ index: number; sku_code: string | null; reason: string }>;
}

// The bulk endpoint's limit. One request per SKU used to trip the 300/min rate limit.
const BATCH_SIZE = 500;

// Catalogue exports' own names, after header normalisation ("Selling Price (INR)" → selling_price_inr).
const PRICE_COLUMN = /^(unit_price|selling_price|sale_price)(_[a-z]{3})?$/;
const COST_COLUMN = /^(unit_cost|cost_price|cost)(_[a-z]{3})?$/;
const GTIN_COLUMN = /^(gtin|barcode|ean|ean13|upc)(_(ean|ean13|upc|gtin))?$/;
const INACTIVE_STATUSES = new Set(["inactive", "draft", "discontinued", "archived"]);

function column(row: ParsedRow, pattern: RegExp): string | undefined {
  const key = Object.keys(row).find((k) => pattern.test(k) && row[k] !== "");
  return key === undefined ? undefined : row[key];
}

const numberOrUndefined = (value: string | undefined) => (value ? Number(value) : undefined);

function toBulkRow(row: ParsedRow): SkuCreateBody & { product?: string; is_active: boolean } {
  const attributes: Record<string, string | number> = {};
  for (const field of ["warehouse_inventory", "forecast_demand", "monthly_sales", "lead_time"]) {
    if (row[field]) attributes[field] = Number(row[field]);
  }
  const color = row.color || row.colour;
  if (color) attributes.color = color;

  return {
    // A product's own code; a "Product ID" column in an export holds that code, not our id.
    product: row.product_external_id || row.product_code || row.product_id || undefined,
    sku_code: row.sku_code,
    external_id: row.external_id || undefined,
    gtin: column(row, GTIN_COLUMN),
    description: row.description || undefined,
    unit_cost: numberOrUndefined(column(row, COST_COLUMN)),
    unit_price: numberOrUndefined(column(row, PRICE_COLUMN)),
    currency: row.currency ? row.currency.trim().toUpperCase() : undefined,
    lead_time_days: numberOrUndefined(row.lead_time_days || row.lead_time),
    moq: row.moq ? Number(row.moq) : 1,
    safety_stock: row.safety_stock ? Number(row.safety_stock) : 0,
    reorder_point: row.reorder_point ? Number(row.reorder_point) : 0,
    attributes: Object.keys(attributes).length > 0 ? attributes : undefined,
    is_active: !INACTIVE_STATUSES.has((row.status ?? "").trim().toLowerCase()),
  };
}

export const skusApi = {
  listAll: (): Promise<Sku[]> => cataloguePages((limit, offset) => skusApi.list({ limit, offset, active_only: false })),
  list: (params?: { limit?: number; offset?: number; active_only?: boolean }) =>
    apiClient.get<Sku[]>("/skus", { params }).then((r) => r.data),
  get: (id: string) => apiClient.get<Sku>(`/skus/${id}`).then((r) => r.data),
  create: (productId: string, body: SkuCreateBody) =>
    apiClient
      .post<Sku>(`/skus/${productId}/skus`, body)
      .then((r) => r.data),
  update: (id: string, body: Partial<SkuCreateBody> & { is_active?: boolean }) =>
    apiClient.patch<Sku>(`/skus/${id}`, body).then((r) => r.data),
  remove: (id: string) =>
    apiClient.delete<{ deleted: boolean; id: string }>(`/skus/${id}`).then((r) => r.data),
  deleteMany: (ids: string[]) =>
    apiClient
      .post<{ deleted: number }>("/skus/bulk-delete", { sku_ids: ids })
      .then((r) => r.data),
  deleteAll: () =>
    apiClient
      .delete<{ deleted: number }>("/skus/all")
      .then((r) => r.data),

  bulkCreate: async (
    rows: ParsedRow[],
    onProgress: (done: number, total: number) => void,
  ): Promise<BulkImportResult> => {
    const result: BulkImportResult = { created: 0, skipped: 0, failed: 0, errors: [] };

    for (let i = 0; i < rows.length; i += BATCH_SIZE) {
      const batch = rows.slice(i, i + BATCH_SIZE);
      try {
        const { data } = await apiClient.post<BulkRowResult>("/skus/bulk", { rows: batch.map(toBulkRow) });
        result.created += data.created;
        result.skipped += data.skipped;
        result.failed += data.failed;
        for (const e of data.errors) result.errors.push({ row: batch[e.index], reason: e.reason });
      } catch (err: unknown) {
        const reason = getErrorMessage(err, "Import request failed");
        result.failed += batch.length;
        for (const row of batch) result.errors.push({ row, reason });
      }
      onProgress(Math.min(i + BATCH_SIZE, rows.length), rows.length);
    }

    return result;
  },
};
