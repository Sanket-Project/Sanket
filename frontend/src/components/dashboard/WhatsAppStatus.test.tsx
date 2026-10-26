import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DeliveryStatus, WhatsAppConfig } from "@/api/notifications";

const api = vi.hoisted(() => ({ getWhatsApp: vi.fn() }));
vi.mock("@/api/notifications", () => ({ notificationsApi: api }));

import { WhatsAppStatus } from "@/components/dashboard/WhatsAppStatus";
import { whatsAppReadiness } from "@/utils/whatsAppReadiness";

/**
 * Audit F11: the dashboard said "Digest enabled" as a hard-coded string while
 * the configuration was disabled, the provider was the console logger and no
 * credentials existed.
 */
const config = (over: Partial<WhatsAppConfig> = {}): WhatsAppConfig => ({
  enabled: true, recipients: [{ phone: "+910000000000", name: "Buyer", role: null }],
  send_hour: 8, timezone: "Asia/Kolkata", min_confidence: 60, max_items: 5, include_alerts: true, ...over,
});
const delivery = (over: Partial<DeliveryStatus> = {}): DeliveryStatus => ({
  provider: "meta", configured: true, detail: "", ...over,
});

describe("whatsAppReadiness", () => {
  it.each([
    [config({ enabled: false }), delivery(), "disabled", "Digest disabled"],
    [config(), delivery({ provider: "console", configured: false }), "preview_only", "Preview only — delivery not connected"],
    [config({ recipients: [] }), delivery(), "no_recipients", "No recipients"],
    [config(), delivery(), "ready", "Delivery configured"],
  ])("derives the state from the real configuration", (cfg, del, state, label) => {
    expect(whatsAppReadiness({ config: cfg, delivery: del }, false)).toMatchObject({ state, label });
  });

  it("does not claim anything when the status cannot be read", () => {
    expect(whatsAppReadiness(undefined, true)).toMatchObject({ state: "error", label: "Status unavailable" });
  });
});

describe("WhatsAppStatus", () => {
  beforeEach(() => api.getWhatsApp.mockReset());

  it("shows what the API reports, not a hard-coded 'enabled'", async () => {
    api.getWhatsApp.mockResolvedValue({ config: config({ enabled: false }),
      delivery: delivery({ provider: "console", configured: false }) });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <WhatsAppStatus />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Digest disabled")).toBeInTheDocument();
    expect(screen.queryByText(/Digest enabled/)).not.toBeInTheDocument();
  });
});
