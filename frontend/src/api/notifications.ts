import { apiClient } from "@/api/client";

export interface WhatsAppRecipient {
  phone: string;
  name: string | null;
  role: string | null;
}

export interface WhatsAppConfig {
  enabled: boolean;
  recipients: WhatsAppRecipient[];
  send_hour: number;
  timezone: string;
  min_confidence: number;
  max_items: number;
  include_alerts: boolean;
}

/**
 * Whether live delivery is actually wired up.
 *
 * `configured: false` means the backend renders and logs the message but does
 * not transmit it — surfaced in the UI so nobody believes a digest went out.
 */
export interface DeliveryStatus {
  provider: "console" | "meta" | "twilio";
  configured: boolean;
  detail: string;
}

export interface DigestItem {
  sku_code: string;
  urgency: string;
  headline: string;
  units: number;
  value: number;
  value_label: string;
  days_of_cover: number | null;
  confidence: number;
  reason: string;
}

export interface DigestPreview {
  digest: {
    tenant_name: string;
    industry: string;
    currency: string;
    items: DigestItem[];
    open_alerts: number;
    total_units: number;
    /** null while any order has no recorded value (see unvalued). */
    total_value: number | null;
    unvalued?: number;
    more_count: number;
    generated_at: string;
    empty_reason: string | null;
  };
  body: string;
  characters: number;
  would_send: boolean;
  recipients: WhatsAppRecipient[];
  delivery: DeliveryStatus;
}

export interface SendResult {
  to: string;
  success: boolean;
  provider: string;
  provider_message_id: string | null;
  error: string | null;
  sent_at: string;
  body: string;
}

export const notificationsApi = {
  getWhatsApp: (): Promise<{ config: WhatsAppConfig; delivery: DeliveryStatus }> =>
    apiClient.get("/notifications/whatsapp").then((r) => r.data),

  updateWhatsApp: (
    config: WhatsAppConfig,
  ): Promise<{ config: WhatsAppConfig; delivery: DeliveryStatus }> =>
    apiClient.put("/notifications/whatsapp", config).then((r) => r.data),

  previewDigest: (): Promise<DigestPreview> =>
    apiClient.get("/notifications/whatsapp/preview").then((r) => r.data),

  sendTest: (body: {
    confirm: boolean;
    to?: string;
  }): Promise<{ sent: boolean; dry_run: boolean; body: string; results?: SendResult[]; delivery: DeliveryStatus; detail?: string }> =>
    apiClient.post("/notifications/whatsapp/test", body).then((r) => r.data),
};
