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

/** One checkpoint on the seven-day plan, verified against real data. */
export interface ReadinessMilestone {
  key: string;
  day: number;
  label: string;
  done: boolean;
  blocking: boolean;
  detail: string;
  action: string | null;
  action_route: string | null;
  metrics: Record<string, unknown>;
}

export interface ReadinessResponse {
  industry: string;
  plan_days: number;
  day_of_journey: number | null;
  percent_complete: number;
  milestones_done: number;
  milestones_total: number;
  on_track: boolean;
  blockers: string[];
  next_action: ReadinessMilestone | null;
  milestones: ReadinessMilestone[];
  days: Array<{ day: number; milestones: ReadinessMilestone[]; complete: boolean }>;
}

export const readinessApi = {
  /**
   * The seven-day plan measured against real data — distinct from
   * `onboardingApi.getState`, which only records which wizard screens were
   * completed.
   */
  get: () => apiClient.get<ReadinessResponse>("/onboarding/readiness").then((r) => r.data),
};
