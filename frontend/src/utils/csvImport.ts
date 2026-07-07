import Papa from "papaparse";
import ExcelJS from "exceljs";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ParsedRow {
  [key: string]: string;
}

export interface ParseResult {
  rows: ParsedRow[];
  headers: string[];
  errors: string[];
}

// ─── Product import ───────────────────────────────────────────────────────────

export const PRODUCT_REQUIRED_COLUMNS = ["name", "category"] as const;
export const PRODUCT_ALL_COLUMNS = [
  "name",
  "brand",
  "category",
  "subcategory",
  "external_id",
  "status",
  "warehouse_inventory",
  "lead_time",
  "safety_stock",
  "forecast_demand",
  "monthly_sales",
] as const;

export const SKU_REQUIRED_COLUMNS = ["sku_code"] as const;
export const SKU_ALL_COLUMNS = [
  "product_external_id",
  "sku_code",
  "description",
  "unit_cost",
  "unit_price",
  "currency",
  "lead_time_days",
  "lead_time",
  "moq",
  "safety_stock",
  "reorder_point",
  "gtin",
  "external_id",
  "warehouse_inventory",
  "forecast_demand",
  "monthly_sales",
] as const;

// ─── File parsing ─────────────────────────────────────────────────────────────

function normalizeHeaders(headers: string[]): string[] {
  return headers.map((h) =>
    h
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "_")
      .replace(/[^a-z0-9_]/g, ""),
  );
}

function parseCSV(text: string): ParseResult {
  const result = Papa.parse<ParsedRow>(text, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) =>
      h
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_")
        .replace(/[^a-z0-9_]/g, ""),
  });

  const headers = result.meta.fields ?? [];
  const errors = result.errors.map((e) => `Row ${e.row}: ${e.message}`);

  return {
    rows: (result.data as ParsedRow[]).map((r) => {
      const clean: ParsedRow = {};
      for (const k of Object.keys(r)) clean[k] = String(r[k] ?? "").trim();
      return clean;
    }),
    headers,
    errors,
  };
}

async function parseXLSX(buffer: ArrayBuffer): Promise<ParseResult> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);

  const sheet = workbook.worksheets[0];
  if (!sheet || sheet.rowCount === 0) {
    return { rows: [], headers: [], errors: [] };
  }

  // First row is headers
  const headerRow = sheet.getRow(1);
  const rawHeaders: string[] = [];
  headerRow.eachCell({ includeEmpty: true }, (cell) => {
    rawHeaders.push(String(cell.value ?? ""));
  });
  const headers = normalizeHeaders(rawHeaders);

  const rows: ParsedRow[] = [];
  sheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
    if (rowNumber === 1) return; // skip header row
    const obj: ParsedRow = {};
    let hasData = false;
    headers.forEach((h, i) => {
      const cell = row.getCell(i + 1);
      const val = String(cell.value ?? "").trim();
      obj[h] = val;
      if (val !== "") hasData = true;
    });
    if (hasData) rows.push(obj);
  });

  return { rows, headers, errors: [] };
}

export async function parseFile(file: File): Promise<ParseResult> {
  const ext = file.name.split(".").pop()?.toLowerCase();

  if (ext === "csv") {
    const text = await file.text();
    return parseCSV(text);
  } else if (ext === "xlsx" || ext === "xls") {
    const buffer = await file.arrayBuffer();
    return parseXLSX(buffer);
  } else {
    return {
      rows: [],
      headers: [],
      errors: [`Unsupported file type: .${ext}. Please use .csv or .xlsx`],
    };
  }
}

// ─── Row validation ───────────────────────────────────────────────────────────

export interface ValidationResult {
  valid: ParsedRow[];
  invalid: Array<{ row: ParsedRow; rowIndex: number; reason: string }>;
}

export function validateProductRows(rows: ParsedRow[]): ValidationResult {
  const valid: ParsedRow[] = [];
  const invalid: ValidationResult["invalid"] = [];

  rows.forEach((row, i) => {
    for (const col of PRODUCT_REQUIRED_COLUMNS) {
      if (!row[col] || row[col].trim() === "") {
        invalid.push({ row, rowIndex: i + 2, reason: `Missing required field: "${col}"` });
        return;
      }
    }
    if (row.status && !["active", "seasonal", "clearance", "pre_launch", "discontinued"].includes(row.status)) {
      invalid.push({
        row,
        rowIndex: i + 2,
        reason: `Invalid status "${row.status}" — must be one of: active, seasonal, clearance, pre_launch, discontinued`,
      });
      return;
    }
    // Validate numeric fields
    const numericFields = ["warehouse_inventory", "lead_time", "safety_stock", "forecast_demand", "monthly_sales"];
    for (const field of numericFields) {
      if (row[field] && row[field] !== "" && isNaN(Number(row[field]))) {
        invalid.push({ row, rowIndex: i + 2, reason: `"${field}" must be a number, got "${row[field]}"` });
        return;
      }
    }
    valid.push(row);
  });

  return { valid, invalid };
}

export function validateSkuRows(rows: ParsedRow[]): ValidationResult {
  const valid: ParsedRow[] = [];
  const invalid: ValidationResult["invalid"] = [];

  rows.forEach((row, i) => {
    for (const col of SKU_REQUIRED_COLUMNS) {
      if (!row[col] || row[col].trim() === "") {
        invalid.push({ row, rowIndex: i + 2, reason: `Missing required field: "${col}"` });
        return;
      }
    }
    // Validate numeric fields
    const numericFields = [
      "unit_cost",
      "unit_price",
      "lead_time_days",
      "lead_time",
      "moq",
      "safety_stock",
      "reorder_point",
      "warehouse_inventory",
      "forecast_demand",
      "monthly_sales",
    ];
    for (const field of numericFields) {
      if (row[field] && row[field] !== "" && isNaN(Number(row[field]))) {
        invalid.push({ row, rowIndex: i + 2, reason: `"${field}" must be a number, got "${row[field]}"` });
        return;
      }
    }
    valid.push(row);
  });

  return { valid, invalid };
}

// ─── Template generators ──────────────────────────────────────────────────────

export function downloadProductTemplate() {
  const csv = [
    "name,brand,category,subcategory,external_id,status,warehouse_inventory,lead_time,safety_stock,forecast_demand,monthly_sales",
    "Widget Pro,Acme Corp,Electronics,Gadgets,WGT-001,active,150,14,50,200,450",
    "Summer Dress,StyleCo,Apparel,Women,DRS-002,seasonal,80,21,20,90,180",
  ].join("\n");

  triggerDownload(csv, "products_import_template.csv", "text/csv");
}

export function downloadSkuTemplate() {
  const csv = [
    "product_external_id,sku_code,description,unit_cost,unit_price,currency,lead_time_days,lead_time,moq,safety_stock,reorder_point,gtin,external_id,warehouse_inventory,forecast_demand,monthly_sales",
    "WGT-001,WGT-001-BLK,Widget Pro Black,12.50,24.99,USD,14,,100,50,200,,,150,200,450",
    "WGT-001,WGT-001-WHT,Widget Pro White,12.50,24.99,USD,,14,100,50,200,,,150,200,450",
    "DRS-002,DRS-002-S,Summer Dress Small,18.00,39.99,USD,21,,50,20,80,,,80,90,180",
  ].join("\n");

  triggerDownload(csv, "skus_import_template.csv", "text/csv");
}

function triggerDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
