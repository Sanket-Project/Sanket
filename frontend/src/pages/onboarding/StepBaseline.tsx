import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Sparkles,
  Zap,
} from "@/components/ui/icons";
import { forwardRef, useImperativeHandle, useState } from "react";

import { forecastsApi, type ForecastRefresh } from "@/api/forecasts";
import { Button } from "@/components/ui/Button";
import { getErrorMessage } from "@/utils/errors";
import type { StepHandle, StepProps } from "./types";

export const StepBaseline = forwardRef<StepHandle, StepProps>(function StepBaseline(
  { thisStep, save },
  ref,
) {
  const [runId, setRunId] = useState<string | null>(null);

  const health = useQuery({
    queryKey: ["forecasts", "ml-health"],
    queryFn: forecastsApi.health,
    staleTime: 60_000,
  });
  const mlReady = (health.data?.status ?? "").toLowerCase() === "ok" ||
    (health.data?.status ?? "").toLowerCase() === "healthy";

  const start = useMutation({
    mutationFn: () => forecastsApi.refresh({ force_zero_shot: true }),
    onSuccess: (r) => setRunId(r.refresh?.id ?? null),
  });

  const run = useQuery({
    queryKey: ["onboarding", "baseline", runId],
    queryFn: () => forecastsApi.latest({ view: "summary", limit: 1 }),
    enabled: !!runId,
    refetchInterval: (q) => {
      const s = q.state.data?.refresh?.status;
      return s === "completed" || s === "failed" ? false : 2000;
    },
  });

  const status: ForecastRefresh["status"] | "idle" = start.isError || run.isError ? "failed"
    : runId ? run.data?.refresh?.status ?? start.data?.refresh?.status ?? "pending" : "idle";

  useImperativeHandle(ref, () => ({
    // Finishing completes onboarding regardless of run state — an in-flight run
    // keeps going server-side, and an unavailable ML service shouldn't trap the
    // user. The baseline can always be (re)run from the workspace.
    submit: async () => {
      await save({
        mark_step: thisStep,
        status: "complete",
        current_step: "done",
        step_meta: { run_id: runId, status },
      });
      return true;
    },
  }));

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-line bg-surface p-6">
        <div className="flex items-start gap-4">
          <span
            className={clsx(
              "grid h-12 w-12 shrink-0 place-items-center rounded-2xl",
              status === "completed"
                ? "bg-emerald-50 text-emerald-600"
                : status === "failed"
                ? "bg-rose-50 text-rose-600"
                : "bg-accent-soft text-accent",
            )}
          >
            {status === "completed" ? (
              <CheckCircle2 size={22} aria-hidden="true" />
            ) : status === "failed" ? (
              <AlertTriangle size={22} aria-hidden="true" />
            ) : status === "pending" || status === "running" ? (
              <Loader2 size={22} className="animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles size={22} aria-hidden="true" />
            )}
          </span>

          <div className="min-w-0 flex-1">
            {status === "idle" && (
              <>
                <h3 className="font-heading text-base font-semibold tracking-tight text-content">
                  Generate your first baseline forecast
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-content-subtle">
                  We'll build a baseline from your sales history. Review its input readiness and
                  measured accuracy before using it for orders.
                </p>
              </>
            )}
            {(status === "pending" || status === "running") && (
              <>
                <h3 className="font-heading text-base font-semibold tracking-tight text-content">
                  Building your baseline…
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-content-subtle">
                  Forecasting in progress. This can take a moment for large catalogs — you can
                  finish setup and it'll be ready in your workspace.
                </p>
              </>
            )}
            {status === "completed" && (
              <>
                <h3 className="font-heading text-base font-semibold tracking-tight text-content">
                  Baseline forecast ready
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-content-subtle">
                  Your first plan is generated. Finish setup to review it in the workspace.
                </p>
              </>
            )}
            {status === "failed" && (
              <>
                <h3 className="font-heading text-base font-semibold tracking-tight text-content">
                  Forecast run failed
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-content-subtle">
                  {run.data?.refresh?.error ?? getErrorMessage(run.error ?? start.error,
                    "Something went wrong. You can retry now or from the workspace.")}
                </p>
              </>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-3">
              {status !== "completed" && (
                <Button
                  icon={<Zap size={15} aria-hidden="true" />}
                  loading={start.isPending || status === "pending" || status === "running"}
                  disabled={!mlReady || start.isPending || status === "running" || status === "pending"}
                  onClick={() => start.mutate()}
                >
                  {status === "failed" ? "Retry forecast" : "Generate baseline"}
                </Button>
              )}
              <span
                className={clsx(
                  "inline-flex items-center gap-1.5 text-xs font-medium",
                  mlReady ? "text-content-subtle" : "text-amber-600",
                )}
              >
                <span
                  className={clsx(
                    "h-1.5 w-1.5 rounded-full",
                    mlReady ? "bg-emerald-500" : "bg-amber-500",
                  )}
                  aria-hidden="true"
                />
                {health.isLoading
                  ? "Checking forecast engine…"
                  : mlReady
                  ? "Forecast engine ready"
                  : "Forecast engine unavailable"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});
