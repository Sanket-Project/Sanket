import { apiClient } from "@/api/client";

export type DataQualitySeverity = "critical" | "warning" | "info";
export type DataQualityFix = "dedupe_sales" | "drop_future_sales" | "drop_negative_sales";

export interface DataQualityFinding {
  key: string;
  label: string;
  severity: DataQualitySeverity;
  count: number;
  why_it_matters: string;
  how_to_fix: string;
  sample: Array<Record<string, unknown>>;
  /** Non-null when the issue can be repaired automatically. */
  autofix: DataQualityFix | null;
}

export interface DataQualityReport {
  industry: string;
  health_score: number;
  grade: string;
  checks_run: number;
  issues_found: number;
  critical: number;
  warnings: number;
  fixable_automatically: DataQualityFix[];
  findings: DataQualityFinding[];
  generated_at: string;
}

export interface FixResult {
  action: DataQualityFix;
  dry_run: boolean;
  rows_affected: number;
  applied: boolean;
}

export const dataQualityApi = {
  report: (): Promise<DataQualityReport> =>
    apiClient.get("/data-quality/report").then((r) => r.data),

  /** `confirm: false` (the default) previews the row count without deleting. */
  fix: (action: DataQualityFix, confirm = false): Promise<FixResult> =>
    apiClient.post("/data-quality/fix", { action, confirm }).then((r) => r.data),
};
