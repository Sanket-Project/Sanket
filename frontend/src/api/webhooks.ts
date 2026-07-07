import { apiClient } from "@/api/client";

export interface WebhookEndpoint {
  id: string;
  url: string;
  enabled_events: string[];
  is_active: boolean;
  description: string | null;
  last_delivery_at: string | null;
  failure_count: number;
  created_at: string;
}

export interface WebhookDelivery {
  id: number;
  endpoint_id: string;
  event_type: string;
  event_id: string;
  status: "pending" | "succeeded" | "failed" | "dead_letter";
  attempt_count: number;
  response_status: number | null;
  response_body: string | null;
  payload: Record<string, any>;
  delivered_at: string | null;
  next_retry_at: string | null;
  created_at: string;
}

export const webhooksApi = {
  list: () =>
    apiClient.get<WebhookEndpoint[]>("/webhooks/endpoints").then((r) => r.data),
  create: (body: {
    url: string;
    enabled_events: string[];
    description?: string;
  }) =>
    apiClient
      .post<WebhookEndpoint & { secret: string; warning: string }>(
        "/webhooks/endpoints",
        body,
      )
      .then((r) => r.data),
  update: (
    id: string,
    body: { enabled_events?: string[]; is_active?: boolean; description?: string },
  ) =>
    apiClient
      .patch<{ id: string; updated: string[] }>(`/webhooks/endpoints/${id}`, body)
      .then((r) => r.data),
  remove: (id: string) =>
    apiClient.delete(`/webhooks/endpoints/${id}`).then(() => undefined),
  deliveries: (params?: {
    endpoint_id?: string;
    status?: string;
    limit?: number;
  }) =>
    apiClient
      .get<WebhookDelivery[]>("/webhooks/deliveries", { params })
      .then((r) => r.data),
  retry: (deliveryId: number) =>
    apiClient
      .post<WebhookDelivery>(`/webhooks/deliveries/${deliveryId}/retry`)
      .then((r) => r.data),
};

export const WEBHOOK_EVENT_TYPES = [
  "forecast.run.started",
  "forecast.run.completed",
  "forecast.run.failed",
  "signal.validated",
  "pharma_batch.released",
  "pharma_batch.recalled",
  "subscription.updated",
  "usage.quota_warning",
  "usage.quota_exceeded",
] as const;
