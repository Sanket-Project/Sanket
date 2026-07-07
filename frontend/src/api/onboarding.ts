import { apiClient } from "@/api/client";
import type {
  Invite,
  InviteCreated,
  InviteList,
  InviteRole,
  OnboardingState,
  OnboardingStateUpdate,
  PlanningConfig,
} from "@/types/api";

export const onboardingApi = {
  /** Current setup readiness for the active tenant. */
  getState: () =>
    apiClient.get<OnboardingState>("/onboarding/state").then((r) => r.data),
  /** Persist wizard progress (owner/admin). */
  updateState: (body: OnboardingStateUpdate) =>
    apiClient.put<OnboardingState>("/onboarding/state", body).then((r) => r.data),
};

export const planningApi = {
  getConfig: () =>
    apiClient.get<PlanningConfig>("/planning/config").then((r) => r.data),
  updateConfig: (body: Partial<PlanningConfig>) =>
    apiClient.put<PlanningConfig>("/planning/config", body).then((r) => r.data),
};

export const invitesApi = {
  list: () => apiClient.get<InviteList>("/invites").then((r) => r.data),
  create: (email: string, role: InviteRole) =>
    apiClient.post<InviteCreated>("/invites", { email, role }).then((r) => r.data),
  revoke: (id: string) =>
    apiClient.delete<Invite>(`/invites/${id}`).then((r) => r.data),
};
