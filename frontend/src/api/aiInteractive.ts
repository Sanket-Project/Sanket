import { apiClient } from "./client";
import type { SummaryResult } from "./ai";
import type { SummaryLanguage } from "./communications";

export type ScenarioField = "demand_shock_pct" | "price_change_pct" | "cost_change_pct" | "lead_time_delta_days" | "supplier_outage_weeks";
export type ScenarioAssumptions = Partial<Record<ScenarioField, number>>;
export interface Interpretation {
  state: string;
  reason?: string;
  assumptions: ScenarioAssumptions;
  evidence: { field: ScenarioField; value: number; span: string }[];
  unresolved: string[];
}
export interface DataAnswer extends SummaryResult { message?: string; missing_sources?: string[] }
export const aiInteractiveApi = {
  interpret: (text: string, signal?: AbortSignal, language: SummaryLanguage = "en") => apiClient.post<Interpretation>("/ai/scenarios/interpret", { text, language }, { signal }).then((r) => r.data),
  question: (text: string, signal?: AbortSignal, language: SummaryLanguage = "en") => apiClient.post<DataAnswer>("/ai/data-qa", { text, language }, { signal }).then((r) => r.data),
};
