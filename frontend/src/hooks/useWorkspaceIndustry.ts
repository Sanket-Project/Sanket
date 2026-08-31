import { useTenantIndustry } from "@/hooks/useTenantIndustry";
import type { IndustryCode } from "@/types/api";

/**
 * The workspace's industry, for surfaces that only render once signed in.
 *
 * Everything under `/workspace` and `/onboarding` sits behind `ProtectedRoute`,
 * which renders nothing until the session resolves; `auth.setSession` projects
 * the industry synchronously, before `isAuthenticated` flips. So inside those
 * routes the industry is always present, and this hook states that invariant in
 * one place rather than leaving fifteen components to assert it individually.
 *
 * It throws rather than falling back to a default. A default here would be a
 * silent lie -- it would render a Fashion dashboard for a Pharma workspace,
 * which is the exact failure this whole change exists to prevent. The throw is
 * caught by the route's ErrorBoundary, so a broken invariant shows up as an
 * error instead of as the wrong industry's data.
 *
 * Use `useTenantIndustry()` instead where null is a legitimate state (route
 * guards, anything that can render mid-bootstrap).
 */
export const useWorkspaceIndustry = (): IndustryCode => {
  const industry = useTenantIndustry();
  // Falsy, not `=== null`. The dev-mode bootstrap rehydrates the session from
  // an untyped localStorage blob, so a snapshot written by an older build has
  // no `active_industry` at all and arrives as undefined — which a null check
  // waves through, to be destructured into `INDUSTRY[undefined]` a moment later.
  if (!industry) {
    throw new Error(
      "useWorkspaceIndustry was called outside an authenticated workspace",
    );
  }
  return industry;
};
