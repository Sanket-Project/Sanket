import { apiClient } from "./client";
import type { AlertRule, ShortageAlert } from "@/types/api";

export const shortageAlertsApi = {
  list: (params?: {
    status?: string;
    severity?: string;
    hours?: number;
    limit?: number;
  }) =>
    apiClient
      .get<ShortageAlert[]>("/alerts", { params })
      .then((r) => r.data),

  acknowledge: (id: string, note?: string) =>
    apiClient
      .patch<ShortageAlert>(`/alerts/${id}/acknowledge`, {
        resolution_note: note,
      })
      .then((r) => r.data),

  resolve: (id: string, note?: string) =>
    apiClient
      .patch<ShortageAlert>(`/alerts/${id}/resolve`, {
        resolution_note: note,
      })
      .then((r) => r.data),

  listRules: () =>
    apiClient.get<AlertRule[]>("/alerts/rules").then((r) => r.data),

  updateRule: (id: string, body: Partial<AlertRule>) =>
    apiClient
      .put<AlertRule>(`/alerts/rules/${id}`, body)
      .then((r) => r.data),

  createRule: (body: Partial<AlertRule> & { rule_name: string }) =>
    apiClient.post<AlertRule>("/alerts/rules", body).then((r) => r.data),
};
