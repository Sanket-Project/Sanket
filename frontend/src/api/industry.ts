import { apiClient } from "@/api/client";
import type {
  EffectiveIndustryConfig,
  IndustryCode,
  IndustryContext,
  IndustryProfileUpdate,
  OverviewKPIs,
} from "@/types/api";

export const industryApi = {
  context: () =>
    apiClient.get<IndustryContext>("/industry/context").then((r) => r.data),
  available: () =>
    apiClient
      .get<Record<string, { display_name: string; default_horizon_weeks: number; audit_level: string }>>(
        "/industry/available",
      )
      .then((r) => r.data),
  overview: (industry: IndustryCode) =>
    apiClient.get<OverviewKPIs>(`/${industry}/overview`).then((r) => r.data),
  profile: () =>
    apiClient.get<EffectiveIndustryConfig>("/industry/profile").then((r) => r.data),
  updateProfile: (body: IndustryProfileUpdate) =>
    apiClient.put<EffectiveIndustryConfig>("/industry/profile", body).then((r) => r.data),
  /**
   * Set the tenant's primary/active industry (onboarding step 1).
   *
   * Returns a re-minted `access_token` in dev-fallback mode. The `ind` claim
   * is baked in at login, so without swapping the token the rest of the
   * session is served the signup-default industry on any request that does not
   * carry an X-Industry-Code override — for a pharma tenant that means
   * standard audit level behind a "21 CFR Part 11" badge. Callers must hand
   * the token to `useAuthStore.replaceToken`.
   */
  activate: (code: IndustryCode) =>
    apiClient
      .post<{ active_industry: IndustryCode; access_token?: string; expires_in?: number }>(
        "/industry/activate",
        { code },
      )
      .then((r) => r.data),
};
