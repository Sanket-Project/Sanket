import { apiClient } from "./client";

export type SummaryLanguage = "en" | "hi" | "te" | "ta";
export interface CommunicationPreferenceValue {
  language: SummaryLanguage;
  weekly_enabled: boolean;
  timezone: string;
  send_hour: number;
}
export interface CommunicationStatus {
  preferences: CommunicationPreferenceValue;
  next_delivery: string | null;
  delivery_available: boolean;
  scheduling_available: boolean;
  last_delivery: { state: string; updated_at: string } | null;
}
export const communicationsApi = {
  preferences: () => apiClient.get<CommunicationStatus>("/communications/preferences").then((r) => r.data),
  save: (body: CommunicationPreferenceValue) => apiClient.put<CommunicationStatus>("/communications/preferences", body).then((r) => r.data),
};
