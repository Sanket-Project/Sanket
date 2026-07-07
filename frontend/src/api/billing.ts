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

export const billingApi = {
  listPlans: () => apiClient.get<Plan[]>("/billing/plans").then((r) => r.data),
  getSubscription: () =>
    apiClient
      .get<SubscriptionSummary | null>("/billing/subscription")
      .then((r) => r.data),
  startSubscription: (body: {
    plan_id: string;
    billing_email: string;
    trial_days?: number;
  }) =>
    apiClient
      .post<{
        id: string;
        plan_id: string;
        status: string;
        short_url: string | null;
      }>("/billing/subscription", body)
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
