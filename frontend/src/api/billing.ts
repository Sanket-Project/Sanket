import { apiClient } from "@/api/client";

export interface Plan {
  id: string;
  display_name: string;
  tier: "growth" | "scale" | "enterprise";
  base_price_cents: number;
  billing_interval: "month" | "year";
  included_quotas: Record<string, number>;
  overage_rates_cents: Record<string, number>;
}

export interface SubscriptionSummary {
  id: string;
  plan_id: string;
  status: "trialing" | "active" | "past_due" | "paused" | "cancelled" | "incomplete";
  current_period_start: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
}

export interface UsageSnapshot {
  period_start: string | null;
  period_end: string | null;
  meters: Record<
    string,
    { used: number; limit: number | null; pct: number }
  >;
}

export interface BillingConfig {
  configured: boolean;
  key_id: string | null;
}

export const billingApi = {
  getConfig: () => apiClient.get<BillingConfig>("/billing/config").then((r) => r.data),
  listPlans: () => apiClient.get<Plan[]>("/billing/plans").then((r) => r.data),
  getSubscription: () =>
    apiClient
      .get<SubscriptionSummary | null>("/billing/subscription")
      .then((r) => r.data),
  // `trial_days` is intentionally absent: trial length and eligibility are
  // decided server-side from the plan. Sending it has no effect.
  //
  // `return_path` is a relative path, not a full URL. The server joins it to a
  // configured origin to build Razorpay's `callback_url`. Sending a full URL
  // (as `redirect_url` used to) is rejected with a 422 — that parameter is
  // where signed payment results land, so its origin must not be client-chosen.
  startSubscription: (body: {
    plan_id: string;
    billing_email: string;
    return_path?: string;
  }) =>
    apiClient
      .post<{
        id: string;
        plan_id: string;
        status: string;
        short_url: string | null;
        razorpay_subscription_id: string | null;
      }>("/billing/subscription", body)
      .then((r) => r.data),
  verifySubscription: (body: {
    razorpay_subscription_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) =>
    apiClient
      .post<{
        id: string;
        plan_id: string;
        status: string;
        current_period_end: string;
      }>("/billing/subscription/verify", body)
      .then((r) => r.data),
  cancel: (atPeriodEnd = true) =>
    apiClient
      .post<{ id: string; status: string; cancel_at_period_end: boolean }>(
        "/billing/subscription/cancel",
        { at_period_end: atPeriodEnd },
      )
      .then((r) => r.data),
  portalSession: (return_url: string) =>
    apiClient
      .post<{ url: string }>("/billing/portal", { return_url })
      .then((r) => r.data),
  usage: () =>
    apiClient.get<UsageSnapshot>("/billing/usage").then((r) => r.data),
};
