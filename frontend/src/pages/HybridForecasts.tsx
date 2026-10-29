import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Play, Sparkles, TrendingDown, TrendingUp } from "@/components/ui/icons";
import clsx from "clsx";
import toast from "react-hot-toast";
import { hybridForecastApi } from "@/api/hybridForecast";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { ScenarioBands } from "@/components/charts/ScenarioBands";
import { TrendPanel } from "@/components/signals/TrendPanel";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { fmtCompact } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import { ForecastExplainer } from "@/components/charts/ForecastExplainer";
import { ForecastChangeExplanation } from "@/components/charts/ForecastChangeExplanation";
import type { HybridForecast } from "@/types/api";

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued — waiting for a worker…",
  data: "Loading SKUs…",
  fit: "Running ML baseline (Chronos)…",
  ensemble: "Fusing trend signals…",
  validate: "Preparing scenario summary…",
  persist: "Finalizing…",
};

const SCENARIO_COLOR: Record<string, string> = {
  pessimistic: "border-rose-500/20 bg-rose-500/5 text-rose-600 dark:text-rose-400 shadow-rose-500/5",
  base: "border-accent/20 bg-accent/5 text-accent dark:text-accent shadow-sm/5",
  optimistic: "border-emerald-500/20 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400 shadow-emerald-500/5",
};

export const HybridForecastsPage = () => {
  const industry = useWorkspaceIndustry();
  const [horizon, setHorizon] = useState(12);
  const [result, setResult] = useState<HybridForecast | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [staleQueue, setStaleQueue] = useState(false);
  const { subscribe } = useWebSocket();

  // If a run is still only "queued" after a while, no worker is consuming the
  // job — surface that instead of spinning forever with no explanation.
  useEffect(() => {
    setStaleQueue(false);
    if (!runId || stage !== "queued") return;
    const t = window.setTimeout(() => setStaleQueue(true), 40_000);
    return () => window.clearTimeout(t);
  }, [runId, stage]);

  // Enqueue a run; the actual compute happens in the background worker.
  const start = useMutation({
    mutationFn: () =>
      hybridForecastApi.create({
        horizon_weeks: horizon,
        include_alerts: false,
      }),
    onSuccess: ({ run_id }) => {
      setResult(null);
      setStage("queued");
      setRunId(run_id);
    },
    onError: (e: unknown) => {
      toast.error(getErrorMessage(e, "Could not start forecast"));
    },
  });

  // Fallback: poll the run status until it reaches a terminal state. This covers
  // the case where the WebSocket is disconnected. refetchInterval stops once
  // the run completes/fails (or when there's no active run).
  const { data: runStatus } = useQuery({
    queryKey: ["hybridRun", runId],
    enabled: !!runId,
    queryFn: () => hybridForecastApi.get(runId!),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "completed" || s === "failed" ? false : 3000;
    },
  });

  // Primary: react to live WebSocket events for this run (instant, no polling lag).
  useEffect(() => {
    if (!runId) return;
    return subscribe((event) => {
      if ((event.data as { run_id?: string })?.run_id !== runId) return;
      if (event.type === "forecast.run.progress") {
        setStage((event.data as { stage?: string }).stage ?? null);
      } else if (event.type === "forecast.run.completed") {
        void hybridForecastApi.get(runId).then((s) => {
          if (s.result) finishRun(s);
        });
      } else if (event.type === "forecast.run.failed") {
        const err = (event.data as { error?: string }).error;
        toast.error(err ?? "Hybrid forecast failed");
        setRunId(null);
        setStage(null);
      }
    });
     
  }, [runId, subscribe]);

  // React to the polling fallback reaching a terminal state.
  const finishedRef = useRef<string | null>(null);
  function finishRun(s: { run_id: string; result: HybridForecast | null; error: string | null }) {
    if (finishedRef.current === s.run_id) return; // de-dupe WS + poll both firing
    finishedRef.current = s.run_id;
    if (s.result) {
      setResult(s.result);
      toast.success(
        `Trend scenario generated for ${s.result.series.length} SKUs`,
      );
    } else if (s.error) {
      toast.error(s.error);
    }
    setRunId(null);
    setStage(null);
  }
  useEffect(() => {
    if (runStatus?.status === "completed" || runStatus?.status === "failed") {
      finishRun(runStatus);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runStatus?.status]);

  // Busy whenever we're enqueueing or a run is in flight.
  const busy = start.isPending || (!!runId && finishedRef.current !== runId);

  const accent = "var(--chart-forecast)";
  const visibleSeries = result?.series.slice(0, 6) ?? [];

  return (
    <div className="space-y-4" data-industry={industry}>
      {/* ── Page header ── */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 animate-fade-in stagger-1">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-semibold tracking-tight text-content">
              Hybrid Forecasts
            </h1>
            <span
              className="inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[10px] font-bold uppercase tracking-wider text-accent border border-accent/50 dark:text-accent dark:border-accent/20 shadow-sm"
              style={{ background: "rgba(124,58,237,0.07)" }}
            >
              <Sparkles size={11} className="text-accent dark:text-accent animate-pulse" /> Trend-fused
            </span>
          </div>
          <p className="text-sm text-content-muted dark:text-content-subtle leading-relaxed max-w-2xl">
            Scenario only: recent signals adjust the historical baseline using hand-set assumptions. These changes have not been validated to improve accuracy and do not generate shortage alerts.
          </p>
        </div>

      </div>

      <ForecastExplainer />

      {/* ── Configure Run Panel ── */}
      <Card
        title={
          <span className="flex items-center gap-2 text-content dark:text-content">
            <Sparkles size={16} className="text-accent" />
            Trend scenario setup
          </span>
        }
        description="Explore assumed changes to the baseline. Use validated forecasts and current stock for ordering decisions."
        className="card-hover-premium shadow-md shadow-slate-100 dark:shadow-none animate-fade-in stagger-2"
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mt-2">
          <div>
            <label className="label">Forecast Horizon (weeks)</label>
            <Input
              type="number"
              min={1}
              max={52}
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              className="input bg-surface/50 dark:bg-surface/50"
            />
          </div>
          <div>
            <label className="label">Industry Scope</label>
            <div className="input flex items-center justify-between bg-surface/50 dark:bg-surface/50">
              <span className="capitalize font-semibold text-content dark:text-content">{industry}</span>
              <Badge variant="info" className="text-[9px] font-semibold uppercase bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
                {industry}
              </Badge>
            </div>
          </div>
          <div className="flex items-center select-none pt-4 md:pt-8">
            <label className="flex items-center gap-2.5 text-xs font-bold text-content-muted dark:text-content-subtle select-none cursor-not-allowed">
              <input
                type="checkbox"
                checked={false}
                disabled
                title="Operational alerts are disabled for unvalidated scenarios"
                className="w-4 h-4 rounded border-line-strong text-accent focus:ring-accent dark:bg-surface dark:border-line accent-violet-600 tactile-press"
              />
              Generate shortage alerts
            </label>
          </div>
          <div className="flex items-end">
            <Button
              icon={<Play size={14} className="group-hover:translate-x-0.5 transition-transform" />}
              loading={busy}
              onClick={() => start.mutate()}
              className="w-full btn-primary group tactile-press py-3 font-semibold"
            >
              Run scenario
            </Button>
          </div>
        </div>
      </Card>

      {/* ── Running/Pending State ── */}
      {busy && (
        <div
          className="rounded-2xl border p-12 flex flex-col items-center gap-5 glass animate-pulse"
          style={{
            borderColor: "var(--accent-ring)",
          }}
        >
          <div className="relative h-16 w-16 flex items-center justify-center">
            <div className="absolute inset-0 rounded-full border-4 border-accent/20 dark:border-line border-t-violet-500 animate-spin" />
            <Sparkles size={20} className="text-accent animate-bounce" />
          </div>
          <div className="text-center max-w-sm">
            <p className="text-base font-bold text-content dark:text-content">{STAGE_LABEL[stage ?? "queued"] ?? "Synthesizing Demand Projections…"}</p>
            <p className="text-xs text-content-subtle dark:text-content-muted mt-1 leading-relaxed">
              Running in the background — this can take up to a minute. You can keep working; results appear here automatically.
            </p>
            {staleQueue && (
              <div className="mt-4 flex items-start gap-2 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 px-3 py-2.5 text-left">
                <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
                <p className="text-[11px] text-amber-700 dark:text-amber-400 leading-relaxed">
                  Still queued after 40s — the background forecast worker may not be running. Start it
                  alongside the API:{" "}
                  <code className="font-mono bg-amber-100 dark:bg-amber-900/40 px-1 rounded">
                    python -m arq app.workers.forecast_worker.WorkerSettings
                  </code>
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Result Deck ── */}
      {result && !busy && (
        <div className="space-y-6">
          <ForecastChangeExplanation
            explanation={result.explanation}
            sampleCount={result.trend.sample_count}
            dataSource={result.data_source}
          />

          {/* Top-row scenarios */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 animate-fade-in stagger-3">
            <div className="lg:col-span-1 card-hover-premium rounded-2xl transition">
              <TrendPanel score={result.trend} />
            </div>
            
            <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-3 gap-5">
              {(["pessimistic", "base", "optimistic"] as const).map((key) => {
                const s = result.scenarios[key];
                if (!s) return null;
                const Icon =
                  key === "pessimistic"
                    ? TrendingDown
                    : key === "optimistic"
                      ? TrendingUp
                      : Sparkles;
                return (
                  <div
                    key={key}
                    className={clsx(
                      "rounded-2xl border p-5 flex flex-col justify-between card-hover-premium backdrop-blur-md shadow-lg transition duration-300",
                      SCENARIO_COLOR[key],
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <span className="text-[10px] font-semibold tracking-widest uppercase">
                          {s.label}
                        </span>
                        <div className="h-6 w-6 rounded-lg bg-surface/20 dark:bg-black/10 flex items-center justify-center border border-white/10">
                          <Icon size={12} />
                        </div>
                      </div>
                      <div className="text-3xl font-semibold tracking-tight tabular-nums text-content dark:text-content leading-none">
                        {fmtCompact(Math.round(s.horizon_total))}
                      </div>
                      <div className="text-[10px] text-content-subtle dark:text-content-muted mt-1 font-bold">
                        Combined Portfolio · {horizon} Weeks
                      </div>
                    </div>
                    <p className="text-xs text-content-muted dark:text-content-subtle mt-5 leading-relaxed italic border-t border-line dark:border-line pt-3 line-clamp-4">
                      "{s.narrative}"
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Per-SKU Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in stagger-4">
            {visibleSeries.map((s) => (
              <Card
                key={s.sku_id}
                title={
                  <span className="font-mono text-xs text-content dark:text-content-subtle font-bold bg-surface-2 dark:bg-surface-2/80 px-2 py-0.5 rounded border border-line/50 dark:border-line">
                    {s.sku_code ?? s.sku_id.slice(0, 12)}
                  </span>
                }
                description={
                  <span className="flex items-center gap-1 text-xs text-content-subtle mt-0.5">
                    <Sparkles size={11} className="text-accent" />
                    Scenario bands (Low, Median, High). Coverage is unvalidated.
                  </span>
                }
                className="card-hover-premium shadow-md shadow-slate-100 dark:shadow-none"
              >
                <div className="mt-3">
                  <ScenarioBands series={s} accent={accent} height={220} />
                </div>
              </Card>
            ))}
          </div>

          {result.alerts_generated > 0 && (
            <Card className="animate-fade-in stagger-5 border-rose-100/50 dark:border-rose-950/20 bg-rose-50/20 dark:bg-rose-950/5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-sm">
                <div className="flex items-center gap-3">
                  <Badge variant="danger" className="text-[10px] font-bold tracking-wider px-3 py-1 bg-rose-500/10 text-rose-500 dark:text-rose-400 border border-rose-500/20 uppercase animate-pulse">
                    {result.alerts_generated} {result.alerts_generated === 1 ? "Alert" : "Alerts"} Fired
                  </Badge>
                  <span className="text-content-muted dark:text-content-subtle font-medium">
                    Supply chain vulnerabilities detected. Planners should check the Shortage Alerts portal.
                  </span>
                </div>
                <Link
                  to="/workspace/alerts"
                  className="flex items-center gap-1.5 text-xs font-bold text-rose-500 hover:text-rose-600 transition-colors group"
                >
                  Open Alerts Dashboard
                  <ArrowRight size={10} className="group-hover:translate-x-0.5 transition-transform" />
                </Link>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Empty State ── */}
      {!result && !busy && (
        <div
          className="rounded-2xl border p-12 flex flex-col items-center justify-center text-center animate-fade-in stagger-3"
          style={{
            background:
              "var(--surface)",
            borderColor: "var(--border)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div
            className="h-16 w-16 rounded-2xl flex items-center justify-center mb-5 border shadow-md"
            style={{
              background: "var(--accent-soft)",
              borderColor: "var(--accent-ring)",
              boxShadow: "none",
            }}
          >
            <Sparkles size={26} className="text-accent dark:text-accent" />
          </div>
          <div className="max-w-md">
            <h3 className="text-base font-semibold text-content dark:text-content mb-2">No hybrid projections active</h3>
            <p className="text-xs text-content-subtle dark:text-content-subtle leading-relaxed">
              Explore how assumed signal adjustments change the baseline. These scenarios have not demonstrated improved forecast accuracy.
            </p>
          </div>
          
          <div className="flex flex-wrap justify-center items-center gap-6 text-[10px] font-bold uppercase tracking-wider text-content-subtle/80 dark:text-content-muted mt-6 pt-5 border-t border-line dark:border-line w-full max-w-md">
            {[
              { icon: "📊", text: "P10/P50/P90 bands" },
              { icon: "📡", text: "Signal Integration" },
              { icon: "📋", text: "Scenario review" },
            ].map(({ icon, text }) => (
              <span key={text} className="flex items-center gap-2">
                <span className="text-xs">{icon}</span> {text}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// Quick arrow component
const ArrowRight = ({ size, className }: { size: number; className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
);
