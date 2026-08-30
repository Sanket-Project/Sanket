import { apiClient } from "@/api/client";

/**
 * One claim on the ROI dashboard.
 *
 * `value` is deliberately nullable: a metric with no evidence yet reports
 * `null` plus a `basis` explaining what it is waiting for, rather than a
 * plausible-looking zero.
 */
export interface RoiLine {
  key: string;
  label: string;
  value: number | null;
  unit: "currency" | "count" | "percent" | "units";
  basis: string;
  evidence_count: number;
  details: Array<Record<string, unknown>>;
}

export interface RoiSummary {
  industry: string;
  window_days: number;
  currency: string;
  total_value_realized: number;
  lines: RoiLine[];
  adoption: {
    recommendations_accepted: number;
    recommendations_open: number;
  };
  caveat: string;
}

export const roiApi = {
  summary: (windowDays = 90): Promise<RoiSummary> =>
    apiClient.get("/roi/summary", { params: { window_days: windowDays } }).then((r) => r.data),
};
