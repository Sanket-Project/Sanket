import type { DeliveryStatus, WhatsAppConfig } from "@/api/notifications";

export type WhatsAppState = "disabled" | "preview_only" | "no_recipients" | "ready" | "error";

/**
 * Readiness of the morning WhatsApp digest, from the actual configuration.
 *
 * "Preview only" means the digest renders but the provider is the console
 * logger or has no credentials, so nothing would be delivered.
 */
export function whatsAppReadiness(
  data: { config: WhatsAppConfig; delivery: DeliveryStatus } | undefined,
  failed: boolean,
): { state: WhatsAppState; label: string; detail: string } {
  if (failed || !data) {
    return { state: "error", label: "Status unavailable", detail: "The notification settings could not be read." };
  }
  const { config, delivery } = data;
  if (!config.enabled) {
    return { state: "disabled", label: "Digest disabled", detail: "Turn it on in WhatsApp settings." };
  }
  if (!delivery.configured || delivery.provider === "console") {
    return {
      state: "preview_only",
      label: "Preview only — delivery not connected",
      detail: delivery.detail || "Messages are rendered but no provider is configured to send them.",
    };
  }
  if (!config.recipients.length) {
    return { state: "no_recipients", label: "No recipients", detail: "Add at least one recipient." };
  }
  return {
    state: "ready",
    label: "Delivery configured",
    detail: `${config.recipients.length} recipient${config.recipients.length === 1 ? "" : "s"} via ${delivery.provider}.`,
  };
}
