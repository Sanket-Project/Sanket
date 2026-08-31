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
  /**
   * Every industry the platform supports. Public — the signup form needs it
   * before anyone holds a token, and prospects may browse all verticals.
   *
   * Replaces an authenticated `/industry/available`: someone already inside a
   * workspace has exactly one industry and should not be shown a list of the
   * others.
   */
  catalog: () =>
    apiClient
      .get<Record<string, { display_name: string; default_horizon_weeks: number; audit_level: string }>>(
        "/industry/catalog",
      )
      .then((r) => r.data),
  overview: (industry: IndustryCode) =>
    apiClient.get<OverviewKPIs>(`/${industry}/overview`).then((r) => r.data),
  profile: () =>
    apiClient.get<EffectiveIndustryConfig>("/industry/profile").then((r) => r.data),
  updateProfile: (body: IndustryProfileUpdate) =>
    apiClient.put<EffectiveIndustryConfig>("/industry/profile", body).then((r) => r.data),
  /**
   * Correct the workspace's industry during initial setup.
   *
   * Not a switch: it works only while setup is incomplete and the workspace
   * holds no data, and answers 409 after that.
   *
   * Returns a re-minted `access_token` in dev-fallback mode — the `ind` claim
   * is baked into the bearer at login, so without swapping it the rest of the
   * session runs on the old industry. Callers must hand the token to
   * `useAuthStore.replaceToken`. In Firebase mode the server resyncs custom
   * claims and revokes refresh tokens instead, and sets `reauth_required`.
   */
  activate: (code: IndustryCode) =>
    apiClient
      .post<{
        active_industry: IndustryCode;
        access_token?: string;
        expires_in?: number;
        reauth_required?: boolean;
      }>("/industry/activate", { code })
      .then((r) => r.data),
};
