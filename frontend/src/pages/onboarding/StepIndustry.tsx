import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Building2,
  Check,
  Cpu,
  Pill,
  Shirt,
  Wheat,
  Wrench,
} from "@/components/ui/icons";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
  type ReactNode,
} from "react";
import toast from "react-hot-toast";

import { industryApi } from "@/api/industry";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { useAuthStore } from "@/stores/auth";
import type { IndustryCode } from "@/types/api";
import { getErrorMessage } from "@/utils/errors";
import type { StepHandle, StepProps } from "./types";

const ICONS: Record<string, ReactNode> = {
  fashion: <Shirt size={18} aria-hidden="true" />,
  electronics: <Cpu size={18} aria-hidden="true" />,
  pharma: <Pill size={18} aria-hidden="true" />,
  agrocenter: <Wheat size={18} aria-hidden="true" />,
  hardware: <Wrench size={18} aria-hidden="true" />,
};

/**
 * Confirms the industry chosen when the workspace was created.
 *
 * This used to be where the industry was *picked*, from a grid of all five,
 * which is why every new workspace was provisioned with all five and defaulted
 * to Fashion until someone clicked. The choice now happens at signup, so this
 * step's job is to show it and — while setup is still incomplete — let an
 * owner or admin correct a mistake.
 *
 * The correction control is deliberately not shown to ordinary members: they
 * join an existing workspace and never had a choice to make. The server
 * enforces the same rule, and returns 409 once the industry locks.
 */
export const StepIndustry = forwardRef<StepHandle, StepProps>(function StepIndustry(
  { nextStep, thisStep, save, onValidityChange },
  ref,
) {
  const industry = useWorkspaceIndustry();
  const role = useAuthStore((s) => s.role);
  const replaceToken = useAuthStore((s) => s.replaceToken);
  const refreshToken = useAuthStore((s) => s.refresh);

  const canCorrect = role === "owner" || role === "admin";
  const [correcting, setCorrecting] = useState(false);
  const [selected, setSelected] = useState<IndustryCode>(industry);
  const [lockedReason, setLockedReason] = useState<string | null>(null);

  const { data: catalog, isLoading } = useQuery({
    queryKey: ["industry", "catalog"],
    queryFn: industryApi.catalog,
    staleTime: 60 * 60_000,
  });

  useEffect(() => {
    setSelected(industry);
  }, [industry]);

  // The industry is already set, so this step is always satisfied.
  useEffect(() => {
    onValidityChange?.(true);
  }, [onValidityChange]);

  useImperativeHandle(ref, () => ({
    submit: async () => {
      try {
        // Only call the server when the industry actually changed. Advancing
        // the wizard must not fail just because the workspace has since locked.
        if (selected !== industry) {
          const res = await industryApi.activate(selected);
          if (res.access_token) {
            // Dev mode: swap in the re-minted bearer.
            replaceToken(res.access_token);
          } else if (res.reauth_required) {
            // Firebase mode: the server re-stamped custom claims and revoked
            // refresh tokens, so the bearer this page is holding is now dead.
            // Force a fresh ID token before the next call — without it the
            // `save` below 401s and the interceptor signs the user out
            // mid-wizard, losing the step.
            await refreshToken();
          }
        }
        await save({
          mark_step: thisStep,
          current_step: nextStep,
          step_meta: { industry: selected },
        });
        return true;
      } catch (err) {
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 409) {
          // Locked between render and submit — show why, in place, and keep
          // the wizard on this step rather than bouncing a toast.
          setLockedReason(getErrorMessage(err, "This workspace's industry is fixed."));
          setCorrecting(false);
          setSelected(industry);
          return false;
        }
        toast.error(getErrorMessage(err, "Could not update the industry"));
        return false;
      }
    },
  }));

  const current = catalog?.[industry];

  if (isLoading) {
    return <div className="h-[88px] animate-pulse rounded-2xl bg-surface-3" />;
  }

  if (!correcting) {
    return (
      <div className="space-y-3">
        <div className="flex items-start gap-3.5 rounded-2xl border border-accent bg-accent-soft p-4">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-fg">
            {ICONS[industry] ?? <Building2 size={18} aria-hidden="true" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-heading text-sm font-semibold tracking-tight text-content">
                {current?.display_name ?? industry}
              </span>
              <Check size={15} className="text-accent" aria-hidden="true" />
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-content-subtle">
              {current && (
                <>
                  <span>{current.default_horizon_weeks}-wk horizon</span>
                  <span className="capitalize">{current.audit_level} audit</span>
                </>
              )}
            </div>
          </div>
        </div>

        <p className="text-xs text-content-subtle">
          This workspace is configured for {current?.display_name ?? industry}.
          Everyone you invite plans in the same industry.
        </p>

        {lockedReason && (
          <p className="text-xs text-danger" role="alert">
            {lockedReason}
          </p>
        )}

        {canCorrect && !lockedReason && (
          <button
            type="button"
            onClick={() => setCorrecting(true)}
            className="text-xs font-medium text-accent underline underline-offset-2"
          >
            Change industry
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-content-subtle">
        Pick the industry this workspace plans for. It can only be changed until
        you finish setup or add data.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(catalog ?? {}).map(([code, meta]) => {
          const isSel = selected === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => setSelected(code as IndustryCode)}
              aria-pressed={isSel}
              className={clsx(
                "group relative flex items-start gap-3.5 rounded-2xl border p-4 text-left tactile-press",
                isSel
                  ? "border-accent bg-accent-soft shadow-sm"
                  : "border-line bg-surface hover:border-line-strong hover:shadow-sm",
              )}
            >
              <span
                className={clsx(
                  "grid h-10 w-10 shrink-0 place-items-center rounded-xl",
                  isSel ? "bg-accent text-accent-fg" : "bg-surface-3 text-content-muted",
                )}
              >
                {ICONS[code] ?? <Building2 size={18} aria-hidden="true" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-heading text-sm font-semibold tracking-tight text-content">
                    {meta.display_name}
                  </span>
                  {isSel && <Check size={15} className="text-accent" aria-hidden="true" />}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-content-subtle">
                  <span>{meta.default_horizon_weeks}-wk horizon</span>
                  <span className="capitalize">{meta.audit_level} audit</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => {
          setSelected(industry);
          setCorrecting(false);
        }}
        className="text-xs font-medium text-content-subtle underline underline-offset-2"
      >
        Keep {current?.display_name ?? industry}
      </button>
    </div>
  );
});
