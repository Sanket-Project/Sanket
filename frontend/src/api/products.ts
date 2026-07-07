import { apiClient } from "@/api/client";
import type { Product } from "@/types/api";
import type { ParsedRow } from "@/utils/csvImport";

export interface ProductCreateBody {
  external_id?: string | null;
  name: string;
  brand?: string | null;
  category: string;
  subcategory?: string | null;
  status?: string;
  attributes?: Record<string, unknown>;
}

export interface BulkImportResult {
  created: number;
  skipped: number;
  failed: number;
  errors: Array<{ row: ParsedRow; reason: string }>;
}

const BATCH_SIZE = 20;

export const productsApi = {
  list: (limit = 50, offset = 0) =>
    apiClient
      .get<Product[]>("/products", { params: { limit, offset } })
      .then((r) => r.data),
  get: (id: string) =>
    apiClient.get<Product>(`/products/${id}`).then((r) => r.data),
  create: (body: ProductCreateBody) =>
    apiClient.post<Product>("/products", body).then((r) => r.data),
  update: (id: string, body: Partial<ProductCreateBody>) =>
    apiClient.patch<Product>(`/products/${id}`, body).then((r) => r.data),
  remove: (id: string) =>
    apiClient
      .delete<{ deleted: boolean; id: string; cascaded_skus: number }>(`/products/${id}`)
      .then((r) => r.data),

  bulkCreate: async (
    rows: ParsedRow[],
    onProgress: (done: number, total: number) => void,
  ): Promise<BulkImportResult> => {
    const result: BulkImportResult = { created: 0, skipped: 0, failed: 0, errors: [] };
    let done = 0;

    for (let i = 0; i < rows.length; i += BATCH_SIZE) {
      const batch = rows.slice(i, i + BATCH_SIZE);
      await Promise.all(
        batch.map(async (row) => {
          try {
            const attributes: Record<string, number> = {};
            const extraFields = ["warehouse_inventory", "lead_time", "safety_stock", "forecast_demand", "monthly_sales"];
            for (const f of extraFields) {
              if (row[f] && row[f] !== "") {
                attributes[f] = Number(row[f]);
              }
            }

            const body: ProductCreateBody = {
              name: row.name,
              category: row.category,
              brand: row.brand || undefined,
              subcategory: row.subcategory || undefined,
              external_id: row.external_id || undefined,
              status: row.status || "active",
              attributes: Object.keys(attributes).length > 0 ? attributes : undefined,
            };
            await apiClient.post<Product>("/products", body);
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
