import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Play, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
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
import { useIndustryStore } from "@/stores/industry";
import { industryAccent } from "@/utils/colors";
import { fmtCompact } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import { ForecastExplainer } from "@/components/charts/ForecastExplainer";
import type { HybridForecast } from "@/types/api";

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued — waiting for a worker…",
  data: "Loading SKUs…",
  fit: "Running ML baseline (Chronos)…",
  ensemble: "Fusing trend signals…",
  validate: "Scanning for shortages…",
  persist: "Finalizing…",
};

const SCENARIO_COLOR: Record<string, string> = {
  pessimistic: "border-rose-500/20 bg-rose-500/5 text-rose-600 dark:text-rose-400 shadow-rose-500/5",
  base: "border-violet-500/20 bg-violet-500/5 text-violet-600 dark:text-violet-400 shadow-violet-500/5",
  optimistic: "border-emerald-500/20 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400 shadow-emerald-500/5",
};

export const HybridForecastsPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const [horizon, setHorizon] = useState(12);
  const [includeAlerts, setIncludeAlerts] = useState(true);
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
        include_alerts: includeAlerts,
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
        `Hybrid forecast generated — ${s.result.series.length} SKUs, ${s.result.alerts_generated} alerts`,
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

  const accent = industryAccent[industry];
  const visibleSeries = result?.series.slice(0, 6) ?? [];

  return (
    <div className="space-y-4" data-industry={industry}>
      {/* ── Page header ── */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 animate-fade-in stagger-1">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 dark:from-white dark:via-slate-200 dark:to-white bg-clip-text text-transparent">
              Hybrid Forecasts
            </h1>
            <span
              className="inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[10px] font-bold uppercase tracking-wider text-violet-600 border border-violet-200/50 dark:text-violet-400 dark:border-violet-500/20 shadow-sm"
              style={{ background: "rgba(124,58,237,0.07)" }}
            >
              <Sparkles size={11} className="text-violet-500 dark:text-violet-400 animate-pulse" /> Trend-fused
            </span>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed max-w-2xl">
            Historical sales baseline projections fused in real-time with live macroeconomic signals, social buzz indices, and search metrics for adaptive inventory matching.
          </p>
        </div>

        {result && (
          <div className="flex items-center gap-3 self-start md:self-center">
            <span
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold border shadow-sm"
              style={{
                background:
                  result.explanation.median_shift_pct >= 0
                    ? "rgba(16,185,129,0.06)"
                    : "rgba(239,68,68,0.06)",
                borderColor:
                  result.explanation.median_shift_pct >= 0
                    ? "rgba(16,185,129,0.2)"
                    : "rgba(239,68,68,0.2)",
                color:
                  result.explanation.median_shift_pct >= 0 ? "#10b981" : "#f43f5e",
              }}
            >
              Median Shift: {result.explanation.median_shift_pct >= 0 ? "+" : ""}
              {(result.explanation.median_shift_pct * 100).toFixed(1)}%
            </span>
            <span
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold border shadow-sm"
              style={{
                background: "rgba(251,191,36,0.06)",
                borderColor: "rgba(251,191,36,0.2)",
                color: "#d97706",
              }}
            >
              Band Deviation: {result.explanation.band_change_pct >= 0 ? "+" : ""}
              {(result.explanation.band_change_pct * 100).toFixed(1)}%
            </span>
          </div>
        )}
      </div>

      <ForecastExplainer />

      {/* ── Configure Run Panel ── */}
      <Card
        title={
          <span className="flex items-center gap-2 text-slate-800 dark:text-slate-100">
            <Sparkles size={16} className="text-violet-500" />
            Adaptive Synthesis Setup
          </span>
        }
        description="Fuses active ensemble parameters with current market drivers."
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
              className="input bg-white/50 dark:bg-slate-900/50"
            />
          </div>
          <div>
            <label className="label">Industry Scope</label>
            <div className="input flex items-center justify-between bg-white/50 dark:bg-slate-900/50">
              <span className="capitalize font-semibold text-slate-700 dark:text-slate-200">{industry}</span>
              <Badge variant="info" className="text-[9px] font-extrabold uppercase bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20">
                {industry}
              </Badge>
            </div>
          </div>
          <div className="flex items-center select-none pt-4 md:pt-8">
            <label className="flex items-center gap-2.5 text-xs font-bold text-slate-500 dark:text-slate-400 select-none cursor-pointer">
              <input
                type="checkbox"
                checked={includeAlerts}
                onChange={(e) => setIncludeAlerts(e.target.checked)}
                className="w-4 h-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500 dark:bg-slate-900 dark:border-slate-800 accent-violet-600 tactile-press"
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
              Run hybrid forecast
            </Button>
          </div>
        </div>
      </Card>

      {/* ── Running/Pending State ── */}
      {busy && (
        <div
          className="rounded-3xl border p-12 flex flex-col items-center gap-5 glass animate-pulse"
          style={{
            borderColor: "rgba(124,58,237,0.15)",
          }}
        >
          <div className="relative h-16 w-16 flex items-center justify-center">
            <div className="absolute inset-0 rounded-full border-4 border-violet-100 dark:border-slate-800 border-t-violet-500 animate-spin" />
            <Sparkles size={20} className="text-violet-500 animate-bounce" />
          </div>
          <div className="text-center max-w-sm">
            <p className="text-base font-bold text-slate-800 dark:text-white">{STAGE_LABEL[stage ?? "queued"] ?? "Synthesizing Demand Projections…"}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 leading-relaxed">
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
                      "rounded-3xl border p-5 flex flex-col justify-between card-hover-premium backdrop-blur-md shadow-lg transition duration-300",
                      SCENARIO_COLOR[key],
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <span className="text-[10px] font-extrabold tracking-widest uppercase">
                          {s.label}
                        </span>
                        <div className="h-6 w-6 rounded-lg bg-white/20 dark:bg-black/10 flex items-center justify-center border border-white/10">
                          <Icon size={12} />
                        </div>
                      </div>
                      <div className="text-3xl font-extrabold tracking-tight tabular-nums text-slate-800 dark:text-white leading-none">
                        {fmtCompact(Math.round(s.horizon_total))}
                      </div>
                      <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 font-bold">
                        Combined Portfolio · {horizon} Weeks
                      </div>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-5 leading-relaxed italic border-t border-slate-100 dark:border-slate-800 pt-3 line-clamp-4">
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
                  <span className="font-mono text-xs text-slate-700 dark:text-slate-300 font-bold bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 rounded border border-slate-200/50 dark:border-slate-800">
                    {s.sku_code ?? s.sku_id.slice(0, 12)}
                  </span>
                }
                description={
                  <span className="flex items-center gap-1 text-xs text-slate-400 mt-0.5">
                    <Sparkles size={11} className="text-violet-400" />
                    Probabilistic band intervals (Low vs Median vs High)
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
                  <span className="text-slate-600 dark:text-slate-400 font-medium">
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
          className="rounded-3xl border p-12 flex flex-col items-center justify-center text-center animate-fade-in stagger-3"
          style={{
            background:
              "linear-gradient(145deg, rgba(255,255,255,0.7) 0%, rgba(245,243,255,0.4) 100%)",
            borderColor: "rgba(226,232,240,0.6)",
            boxShadow: "0 4px 30px rgba(124,58,237,0.02)",
          }}
        >
          <div
            className="h-16 w-16 rounded-2xl flex items-center justify-center mb-5 border shadow-md"
            style={{
              background: "linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)",
              borderColor: "rgba(124,58,237,0.15)",
              boxShadow: "0 8px 24px rgba(124,58,237,0.08)",
            }}
          >
            <Sparkles size={26} className="text-violet-500 dark:text-violet-400" />
          </div>
          <div className="max-w-md">
            <h3 className="text-base font-extrabold text-slate-800 dark:text-white mb-2">No hybrid projections active</h3>
            <p className="text-xs text-slate-400 dark:text-slate-400 leading-relaxed">
              Synthesize historic baseline records with live social sentiment, search momentum, and commodity spikes to predict supply coverage vulnerabilities.
            </p>
          </div>
          
          <div className="flex flex-wrap justify-center items-center gap-6 text-[10px] font-bold uppercase tracking-wider text-slate-400/80 dark:text-slate-500 mt-6 pt-5 border-t border-slate-100 dark:border-slate-800 w-full max-w-md">
            {[
              { icon: "📊", text: "P10/P50/P90 bands" },
              { icon: "📡", text: "Signal Integration" },
              { icon: "🔔", text: "Automatic Shortage Triggers" },
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
