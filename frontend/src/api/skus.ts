import { apiClient } from "@/api/client";
import type { Sku, Product } from "@/types/api";
import type { ParsedRow } from "@/utils/csvImport";
import type { BulkImportResult } from "@/api/products";

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

const BATCH_SIZE = 20;

export const skusApi = {
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

  bulkCreate: async (
    rows: ParsedRow[],
    onProgress: (done: number, total: number) => void,
  ): Promise<BulkImportResult> => {
    const result: BulkImportResult = { created: 0, skipped: 0, failed: 0, errors: [] };
    let done = 0;

    // Build a lookup map: external_id → product_id
    // Fetch all products once upfront
    const productsByExternalId: Record<string, string> = {};
    try {
      const allProducts = await apiClient
        .get<Product[]>("/products", { params: { limit: 1000, offset: 0 } })
        .then((r) => r.data);
      for (const p of allProducts) {
        if (p.external_id) productsByExternalId[p.external_id] = p.id;
      }
    } catch {
      // If fetch fails, individual rows will fail with "product not found"
    }

    for (let i = 0; i < rows.length; i += BATCH_SIZE) {
      const batch = rows.slice(i, i + BATCH_SIZE);
      await Promise.all(
        batch.map(async (row) => {
          try {
            // Resolve product ID
            let productId: string | undefined;
            if (row.product_external_id) {
              productId = productsByExternalId[row.product_external_id];
              if (!productId) {
                result.failed++;
                result.errors.push({
                  row,
                  reason: `No product found with external_id "${row.product_external_id}"`,
                });
                return;
              }
            } else if (row.product_id) {
              productId = row.product_id;
            } else {
              result.failed++;
              result.errors.push({
                row,
                reason: `Missing "product_external_id" — cannot link SKU to a product`,
              });
              return;
            }

            const attributes: Record<string, number> = {};
            if (row.warehouse_inventory && row.warehouse_inventory !== "") {
              attributes.warehouse_inventory = Number(row.warehouse_inventory);
            }
            if (row.forecast_demand && row.forecast_demand !== "") {
              attributes.forecast_demand = Number(row.forecast_demand);
            }
            if (row.monthly_sales && row.monthly_sales !== "") {
              attributes.monthly_sales = Number(row.monthly_sales);
            }
            if (row.lead_time && row.lead_time !== "") {
              attributes.lead_time = Number(row.lead_time);
            }

            const body: SkuCreateBody = {
              sku_code: row.sku_code,
              external_id: row.external_id || undefined,
              gtin: row.gtin || undefined,
              description: row.description || undefined,
              unit_cost: row.unit_cost ? Number(row.unit_cost) : undefined,
              unit_price: row.unit_price ? Number(row.unit_price) : undefined,
              currency: row.currency || "USD",
              lead_time_days: row.lead_time_days
                ? Number(row.lead_time_days)
                : (row.lead_time ? Number(row.lead_time) : undefined),
              moq: row.moq ? Number(row.moq) : 1,
              safety_stock: row.safety_stock ? Number(row.safety_stock) : 0,
              reorder_point: row.reorder_point ? Number(row.reorder_point) : 0,
              attributes: Object.keys(attributes).length > 0 ? attributes : undefined,
            };

            await apiClient.post<Sku>(`/skus/${productId}/skus`, body);
            result.created++;
          } catch (err: unknown) {
            const status = (err as { response?: { status?: number } })?.response?.status;
            if (status === 409) {
              result.skipped++;
            } else {
              result.failed++;
              const msg =
                (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                "Unknown error";
              result.errors.push({ row, reason: msg });
            }
          } finally {
            done++;
            onProgress(done, rows.length);
          }
        }),
      );
    }

    return result;
  },
};
