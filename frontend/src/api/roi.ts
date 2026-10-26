import { apiClient } from "@/api/client";

export type RoiTier = "opportunity" | "estimated_at_approval" | "observed";

/**
 * One figure on the ROI dashboard.
 *
 * `value` is nullable: a metric with no evidence yet reports `null` plus a
 * `basis` saying what it is waiting for, and a money figure spanning several
 * currencies has no single value — read `values_by_currency` instead.
 */
export interface RoiLine {
  key: string;
  label: string;
  tier: RoiTier;
  value: number | null;
  unit: "currency" | "count" | "percent" | "units";
  currency: string | null;
  values_by_currency: Record<string, number>;
  /** False for figures derived from another line; adding them double-counts. */
  additive: boolean;
  basis: string;
  evidence_count: number;
  details: Array<Record<string, unknown>>;
}

export interface RoiTierBlock {
  label: string;
  /** "estimate" | "measured" | "not_measurable" */
  status: string;
  lines: RoiLine[];
}

export interface RoiSummary {
  industry: string;
  window_days: number;
  currency: string | null;
  currencies: string[];
  tiers: Record<RoiTier, RoiTierBlock>;
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
