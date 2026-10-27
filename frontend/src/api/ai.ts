import { apiClient } from "./client";

export type SummaryFeature = "onboarding" | "data_quality" | "decision_explanation" | "alert_explanation" | "planning_brief" | "industry_advice" | "roi_report" | "weekly_summary";
export interface AISettingsValue {
  enabled: boolean;
  sharing: "disabled" | "headers_only" | "redacted_samples";
  tasks: Record<string, boolean>;
  aggregate_context: boolean;
  product_names: boolean;
  can_manage?: boolean;
}
export interface SummaryResult {
  state: string;
  reason?: string;
  blocks: { text: string; kind: string; sources: { fact_id: string; href: string }[] }[];
  snapshot?: string;
}
export interface CleanupChange {
  sku_id: string; field: string; value: string; revision: string;
}
export interface CleanupResult {
  state: string;
  suggestions: { product_id: string; field: string; value: string; evidence: string; confidence: string }[];
  duplicate_pairs: [string, string][];
  products: { id: string; name: string; category: string; attributes: Record<string, unknown>; revision: string }[];
}
export const aiApi = {
  settings: () => apiClient.get<AISettingsValue>("/ai/settings").then((r) => r.data),
  saveSettings: (body: AISettingsValue) => apiClient.put<AISettingsValue>("/ai/settings", body).then((r) => r.data),
  summary: (feature: SummaryFeature, entityId?: string, connector?: string) => apiClient.post<SummaryResult>(`/ai/summary/${feature}`, { entity_id: entityId || null, ...(connector ? { connector } : {}) }).then((r) => r.data),
  cleanup: (skuIds: string[]) => apiClient.post<CleanupResult>("/ai/product-cleanup", { sku_ids: skuIds }).then((r) => r.data),
  applyCleanup: (changes: CleanupChange[], confirm: boolean) => apiClient.post<{ applied: boolean; changes: (CleanupChange & { before: unknown })[] }>("/ai/product-cleanup/confirm", { changes, confirm }).then((r) => r.data),
  importFormats: () => apiClient.get<{ id: string; kind: string; fingerprint: string; revision: number; disabled: boolean }[]>("/ai/import-formats").then((r) => r.data),
  manageFormat: (id: string, revision: number, disabled: boolean | null) => apiClient.post(`/ai/import-formats/${id}`, { expected_revision: revision, disabled }).then((r) => r.data),
};
