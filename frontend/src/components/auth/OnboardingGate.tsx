import { Navigate } from "react-router-dom";
import { type ReactNode } from "react";
import { useAuthStore } from "@/stores/auth";

/**
 * Routes a tenant that hasn't finished setup into the onboarding wizard.
 * Sits inside ProtectedRoute (auth already resolved). A `null` onboarding slice
 * means a legacy/demo tenant — treated as complete, so the workspace renders.
 * `skipped` also renders the workspace (the "Finish setup" banner lives there).
 */
export const OnboardingGate = ({ children }: { children: ReactNode }) => {
  const onboarding = useAuthStore((s) => s.onboarding);

  if (onboarding && onboarding.status === "in_progress") {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
};
