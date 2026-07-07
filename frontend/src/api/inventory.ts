import { apiClient } from "@/api/client";
import type { ParsedRow } from "@/utils/csvImport";

// ── Types ──────────────────────────────────────────────────────────────────

export type OnHandSource = "inventory" | "override" | "fallback";

export interface InventoryLevel {
  sku_id: string;
  sku_code: string;
  location: string;
  on_hand_units: number;
  inbound_units: number;
  reserved_units: number;
  available_units: number;
  as_of: string | null;
  source: string;
}

export interface InventoryLevelsResponse {
  industry: string;
  count: number;
  levels: InventoryLevel[];
}

export interface InventoryUpsertItem {
  sku_id: string;
  on_hand_units: number;
  inbound_units?: number;
  reserved_units?: number;
  location?: string;
  source?: string;
}

export interface InventoryUpsertResponse {
  upserted: number;
  industry: string;
}

// ── API calls ──────────────────────────────────────────────────────────────

export const inventoryApi = {
  /** Fetch current stock positions for the active industry */
  levels: (limit = 500): Promise<InventoryLevelsResponse> =>
    apiClient
      .get("/inventory/levels", { params: { limit } })
      .then((r) => r.data),

  /** Upsert stock positions (used by manual edit and CSV import) */
  upsert: (items: InventoryUpsertItem[]): Promise<InventoryUpsertResponse> =>
    apiClient
      .put("/inventory/levels", { items })
      .then((r) => r.data),
};

// ── CSV import helpers ─────────────────────────────────────────────────────

export const INVENTORY_REQUIRED_COLUMNS = ["sku_code", "on_hand_units"] as const;

export const INVENTORY_OPTIONAL_COLUMNS = [
  "inbound_units",
  "reserved_units",
  "location",
  "source",
] as const;

export function validateInventoryRows(
  rows: ParsedRow[],
  skuCodeToId: Record<string, string>,
) {
  const valid: ParsedRow[] = [];
  const invalid: Array<{ row: ParsedRow; rowIndex: number; reason: string }> = [];

  rows.forEach((row, i) => {
    const rowNum = i + 2;
    if (!row.sku_code?.trim()) {
      invalid.push({ row, rowIndex: rowNum, reason: 'Missing required field: "sku_code"' });
      return;
    }
    if (!row.on_hand_units?.trim()) {
      invalid.push({ row, rowIndex: rowNum, reason: 'Missing required field: "on_hand_units"' });
      return;
    }
    const qty = Number(row.on_hand_units);
    if (isNaN(qty) || qty < 0) {
      invalid.push({
        row,
        rowIndex: rowNum,
        reason: `"on_hand_units" must be a non-negative number, got "${row.on_hand_units}"`,
      });
      return;
    }
    for (const opt of ["inbound_units", "reserved_units"] as const) {
      if (row[opt] && row[opt] !== "" && (isNaN(Number(row[opt])) || Number(row[opt]) < 0)) {
        invalid.push({
          row,
          rowIndex: rowNum,
          reason: `"${opt}" must be a non-negative number, got "${row[opt]}"`,
        });
        return;
      }
    }
    if (skuCodeToId[row.sku_code.trim()] === undefined) {
      invalid.push({
        row,
        rowIndex: rowNum,
        reason: `SKU code "${row.sku_code}" not found in your catalog`,
      });
      return;
    }
    valid.push(row);
  });

  return { valid, invalid };
}

export function downloadInventoryTemplate() {
  const csv = [
    "sku_code,on_hand_units,inbound_units,reserved_units,location",
    "WGT-001-BLK,350,120,0,warehouse-a",
    "WGT-001-WHT,210,0,40,warehouse-a",
    "DRS-002-S,85,0,0,default",
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "inventory_import_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}
