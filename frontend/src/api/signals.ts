import { apiClient } from "@/api/client";
import type { ExternalSignal, SignalStatus, SignalType } from "@/types/api";

export interface SignalCreateBody {
  signal_type: SignalType;
  source_name: string;
  source_url?: string;
  effective_at: string;
  expires_at?: string;
  region?: string;
  category_tags?: string[];
  sku_tags?: string[];
  raw_payload?: Record<string, unknown>;
  processed_value?: number;
  sentiment_score?: number;
  impact_weight?: number;
}

export const signalsApi = {
  list: (params?: {
    status?: SignalStatus;
    signal_type?: SignalType;
    limit?: number;
    offset?: number;
  }) =>
    apiClient
      .get<ExternalSignal[]>("/signals", { params })
      .then((r) => r.data),
  ingest: (body: SignalCreateBody) =>
    apiClient.post<ExternalSignal>("/signals", body).then((r) => r.data),
  validate: (id: string) =>
    apiClient
      .post<ExternalSignal>(`/signals/${id}/validate`)
      .then((r) => r.data),
};
