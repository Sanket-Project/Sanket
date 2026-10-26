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

/** "excess": cover beyond 2 × (lead time + review period) — the decision engine's excess rule. */
export type CoverageStatus = "healthy" | "low" | "critical" | "excess" | "unknown";

/** One location of a SKU. cover_days/status are null unless that location has its own sales. */
export interface LocationCoverage {
  location: string;
  available_units: number;
  on_hand_units: number;
  inbound_units: number;
  as_of: string | null;
  stock_stale: boolean;
  location_demand: { weekly_units: number | null; weeks_observed: number; basis: "location_sales" | null };
  cover_days: number | null;
  status: CoverageStatus | null;
  /** Set for excess stock: what to do instead of reordering. */
  next_action?: string | null;
  reason: string;
  demand_basis?: "forecast" | "trailing_actuals" | null;
  open_transfer?: { units: number; destination: string } | null;
}

export interface SkuCoverage {
  sku_id: string;
  sku_code: string;
  lead_time_days: number;
  lead_time_assumed: boolean;
  demand: { basis: "forecast" | "trailing_actuals" | null; weekly_units: number | null; run_id: string | null; reason: string };
  /** Pooled across every location. */
  sku_wide: {
    available_units: number;
    inbound_units: number;
    cover_days: number | null;
    status: CoverageStatus;
    next_action?: string | null;
    reason: string;
  };
  locations: LocationCoverage[];
}

export interface CoverageResponse {
  industry: string;
  as_of: string;
  calendar: string;
  policy: {
    forecast_max_age_days: number;
    forecast_weeks: number;
    trailing_weeks: number;
    min_weeks: number;
    stale_stock_days: number;
    low_multiplier: number;
    excess_multiplier?: number;
    review_period_days?: number;
    transfer_suggestions: boolean;
  };
  skus: SkuCoverage[];
}

export const inventoryApi = {
  /** Days of cover per SKU (pooled) and per location, from demand and lead time. */
  coverage: (): Promise<CoverageResponse> =>
    apiClient.get("/inventory/coverage").then((r) => r.data),

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
