import { Sparkles, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { onboardingApi } from "@/api/onboarding";
import { useAuthStore } from "@/stores/auth";

/**
 * Persistent, dismissible nudge shown in the workspace when a tenant skipped
 * setup. Resuming flips status back to in_progress so the wizard re-opens at the
 * step where they left off. Owners/admins only (others can't write state).
 */
export const SetupBanner = () => {
  const navigate = useNavigate();
  const onboarding = useAuthStore((s) => s.onboarding);
  const role = useAuthStore((s) => s.role);
  const setOnboarding = useAuthStore((s) => s.setOnboarding);
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);

  const canManage = role === "owner" || role === "admin";
  if (dismissed || !canManage || onboarding?.status !== "skipped") return null;

  const resume = async () => {
    setBusy(true);
    try {
      const next = await onboardingApi.updateState({ status: "in_progress" });
      setOnboarding(next);
      navigate("/onboarding");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-sm">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
        <Sparkles size={16} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-content">Finish setting up your workspace</p>
        <p className="text-xs text-content-subtle">
          Pick up where you left off — connect data, set planning rules, and generate your first plan.
        </p>
      </div>
      <button
        type="button"
        onClick={resume}
        disabled={busy}
        className="btn-primary px-3.5 py-2 text-xs"
      >
        Resume setup
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="rounded-lg p-1.5 text-content-subtle tactile-press hover:bg-surface-3 hover:text-content"
      >
        <X size={15} aria-hidden="true" />
      </button>
    </div>
  );
};
