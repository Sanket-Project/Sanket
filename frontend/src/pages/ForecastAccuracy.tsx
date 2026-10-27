import { useState } from "react";
import { AISummary } from "@/components/ai/AISummary";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart3, CheckCircle2, Circle, Loader2 } from "@/components/ui/icons";
import { forecastAccuracyApi, type ForecastAccuracyResponse } from "@/api/forecastAccuracy";
import { forecastConfidenceApi, forecastsApi } from "@/api/forecasts";
import { salesAnalyticsApi } from "@/api/salesAnalytics";
import { dataQualityApi } from "@/api/dataQuality";
import { Card } from "@/components/ui/Card";
import { CategoryBar } from "@/components/charts/CategoryBar";
import { PageLoader } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getErrorMessage } from "@/utils/errors";
import { backtestCutoffError } from "@/pages/forecastAccuracyRules";

const pct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);
const signedPct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const fmtDay = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );

/** Why forecasts were not scored, in words (keys from GET /forecast/accuracy). */
const EXCLUSION_TEXT: Record<string, (n: number) => string> = {
  generated_after_period_start: (n) => `${n} forecast${n === 1 ? "" : "s"} made after ${n === 1 ? "its" : "their"} week had begun`,
  trained_on_period: (n) => `${n} forecast${n === 1 ? "" : "s"} whose model had already seen that week`,
  period_not_complete: (n) => `${n} for weeks that have not finished yet`,
  awaiting_actuals: (n) => `${n} for weeks the sales feed has not reached yet`,
  legacy_calendar: (n) => `${n} from older runs dated on Sundays, which cannot be matched to a week reliably`,
};


const Exclusions = ({ excluded }: { excluded: ForecastAccuracyResponse["excluded"] }) => {
  const items = Object.entries(excluded ?? {}).filter(([, n]) => n > 0);
  if (!items.length) return null;
  return (
    <Card title="Not scored" description="Forecasts that could not be compared fairly with actual sales">
      <ul className="space-y-1 text-sm text-content-muted">
        {items.map(([reason, n]) => (
          <li key={reason}>{(EXCLUSION_TEXT[reason] ?? ((k: number) => `${k} · ${reason}`))(n)}</li>
        ))}
      </ul>
    </Card>
  );
};

const BacktestPanel = ({ runs }: { runs: ForecastAccuracyResponse["backtest"]["runs"] }) => {
  const industry = useWorkspaceIndustry();
  const qc = useQueryClient();
  const [cutoff, setCutoff] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (c: string) => forecastsApi.backtest({ cutoff: c, horizon: 8 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["forecast-accuracy", industry] }),
    onError: (e) => setError(getErrorMessage(e, "The backtest could not be run.")),
  });

  const submit = () => {
    const problem = backtestCutoffError(cutoff);
    setError(problem);
    if (!problem) run.mutate(cutoff);
  };

  return (
    <Card
      title="Backtests"
      description="Forecasts made after the fact, from history before a past Monday only. Leakage-free, but not production accuracy."
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-content-muted" htmlFor="backtest-cutoff">
          Forecast as if it were (a past Monday)
          <input
            id="backtest-cutoff"
            type="text"
            inputMode="numeric"
            placeholder="YYYY-MM-DD"
            value={cutoff}
            onChange={(e) => setCutoff(e.target.value)}
            className="mt-1 block rounded-lg border border-line bg-surface-2 px-2 py-1.5 font-mono text-sm"
          />
        </label>
        <Button size="sm" variant="secondary" loading={run.isPending} onClick={submit}>
          Run backtest
        </Button>
      </div>
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
      {runs.length > 0 && (
        <ul className="mt-4 divide-y divide-line text-sm">
          {runs.map((r) => (
            <li key={r.run_id} className="flex flex-wrap justify-between gap-2 py-2">
              <span className="font-medium text-content">
                Backtest from {r.cutoff ? fmtDay(r.cutoff) : "unknown cutoff"} · made after the fact
              </span>
              <span className="text-content-muted">
                {r.points} points · {r.skus} SKUs · WAPE {pct(r.wape)} · bias {signedPct(r.bias_pct)} · P10–P90
                coverage {pct(r.coverage_p10_p90)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};

export const ForecastAccuracyPage = () => {
  const industry = useWorkspaceIndustry();

  const { data: accuracy, isLoading, isError } = useQuery({
    queryKey: ["forecast-accuracy", industry],
    queryFn: () => forecastAccuracyApi.list(100),
  });

  const { data: anomalies } = useQuery({
    queryKey: ["anomalies", industry],
    queryFn: () => forecastAccuracyApi.anomalies(90),
  });

  const hasAccuracyRows = (accuracy?.rows.length ?? 0) > 0;
  const readinessEnabled = !isLoading && !isError && !hasAccuracyRows;

  const {
    data: confidence,
    isLoading: confidenceLoading,
    isError: confidenceUnavailable,
  } = useQuery({
    queryKey: ["forecast-confidence", industry, "accuracy-readiness"],
    queryFn: () => forecastConfidenceApi.list(1),
    enabled: readinessEnabled,
  });

  const {
    data: salesHistory,
    isLoading: salesLoading,
    isError: salesUnavailable,
  } = useQuery({
    queryKey: ["sales-timeseries", industry, "week", 90],
    queryFn: () => salesAnalyticsApi.timeseries("week", 90),
    enabled: readinessEnabled,
  });

  const {
    data: quality,
    isLoading: qualityLoading,
    isError: qualityUnavailable,
  } = useQuery({
    queryKey: ["data-quality", industry],
    queryFn: dataQualityApi.report,
    enabled: readinessEnabled,
  });

  if (isLoading) return <PageLoader />;
  if (isError) return <Card title="Accuracy unavailable"><p>Could not load accuracy results. Try again later.</p></Card>;

  const rows = accuracy?.rows ?? [];
  const backtests = accuracy?.backtest.runs ?? [];

  if (rows.length === 0) {
    const hasForecastRun = Boolean(confidence?.run_id);
    // A zero-filled window is not history; any recorded bucket is.
    const hasSalesHistory = (salesHistory?.series ?? []).some((point) => point.units_sold != null);
    const hasHealthyInputs = Boolean(quality && quality.critical === 0);
    const completedRequirements = [hasForecastRun, hasSalesHistory, hasHealthyInputs].filter(Boolean).length;

    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Production accuracy</h1>
        <AccuracyReadiness
          completedRequirements={completedRequirements}
          forecast={{
            complete: hasForecastRun,
            loading: confidenceLoading,
            unavailable: confidenceUnavailable,
            detail: hasForecastRun
              ? "A completed forecast run is available."
              : confidence?.reason ?? "Run a forecast to establish the prediction baseline.",
          }}
          sales={{
            complete: hasSalesHistory,
            loading: salesLoading,
            unavailable: salesUnavailable,
            detail: hasSalesHistory
              ? `${salesHistory?.series.length ?? 0} weekly sales bucket${salesHistory?.series.length === 1 ? " is" : "s are"} available; accuracy waits for actuals recorded after the forecast.`
              : "No weekly sales history was found in the last 90 days.",
          }}
          quality={{
            complete: hasHealthyInputs,
            loading: qualityLoading,
            unavailable: qualityUnavailable,
            detail: quality
              ? `${quality.health_score}/100 health score · ${quality.critical} critical issue${quality.critical === 1 ? "" : "s"}.`
              : "Data-quality status has not been verified yet.",
          }}
        />
        {accuracy && <Exclusions excluded={accuracy.excluded} />}
        <BacktestPanel runs={backtests} />
      </div>
    );
  }

  // Average WAPE by model for the bar chart (WAPE is undefined when nothing sold)
  const byModel: Record<string, number[]> = {};
  for (const row of rows) {
    if (row.wape !== null) (byModel[row.model_name] ??= []).push(row.wape);
  }
  const modelAvg = Object.entries(byModel).map(([model, values]) => ({
    category: model,
    count: Math.round(values.reduce((a, b) => a + b, 0) / values.length),
  }));
  const summary = accuracy?.summary;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-[var(--accent)] text-sm font-medium uppercase tracking-wider">
            <BarChart3 size={14} /> Forecast Accuracy
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Production accuracy</h1>
          <p className="text-slate-500 mt-1 max-w-2xl">
            Each forecast week (Monday, UTC) compared with what sold that week, using only forecasts
            made before the week began. {summary?.points ?? 0} SKU-weeks across {summary?.skus ?? 0} SKUs.
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-400 uppercase tracking-wide">Portfolio WAPE</p>
          <p className="text-2xl font-bold text-content">{pct(summary?.wape)}</p>
          <p className="text-xs text-content-muted">
            bias {signedPct(summary?.bias_pct)} · P10–P90 coverage {pct(summary?.coverage_p10_p90)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Average WAPE by model" description="Lower is better">
          {modelAvg.length > 0 ? (
            <CategoryBar data={modelAvg} accent="var(--accent)" />
          ) : (
            <p className="text-slate-400 text-sm py-8 text-center">No demand in the scored weeks — WAPE is undefined.</p>
          )}
        </Card>

        <Card className="lg:col-span-2" title="Per-SKU accuracy" description="Sorted by WAPE, lowest first">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {["SKU", "Model", "WAPE", "Bias", "P10–P90 coverage", "Weeks"].map((h) => (
                    <th key={h} className="text-left py-2 px-3 text-slate-500 font-medium text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 30).map((row) => (
                  <tr key={`${row.sku_id}-${row.model_name}`} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="py-2 px-3 font-mono text-xs text-slate-600">{row.sku_code ?? `${row.sku_id.slice(0, 8)}…`}</td>
                    <td className="py-2 px-3"><Badge>{row.model_name}</Badge></td>
                    <td className="py-2 px-3 font-semibold">{pct(row.wape)}</td>
                    <td className="py-2 px-3 text-slate-500">{signedPct(row.bias_pct)}</td>
                    <td className="py-2 px-3 text-slate-500">{pct(row.coverage_p10_p90)}</td>
                    <td className="py-2 px-3 text-slate-500">{row.n_obs}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {accuracy && <Exclusions excluded={accuracy.excluded} />}
      <BacktestPanel runs={backtests} />

      {/* Anomaly log */}
      {anomalies && anomalies.sku_count > 0 && (
        <Card title={`Demand anomalies — ${anomalies.sku_count} SKUs flagged`} description={`Last ${anomalies.window_days} days · STL + Isolation Forest`}>
          <div className="space-y-3">
            {anomalies.anomalous_skus.slice(0, 10).map((sku) => (
              <div key={sku.sku_id} className="flex items-center justify-between border border-amber-100 bg-amber-50/50 rounded-lg px-4 py-3">
                <div>
                  <p className="text-sm font-mono text-slate-700">{sku.sku_id.slice(0, 8)}…</p>
                  <p className="text-xs text-slate-400">{sku.anomaly_count} anomalous weeks · last {sku.latest_anomaly_date}</p>
                  <AISummary feature="alert_explanation" entityId={sku.sku_id} connector="anomaly" contextKey={JSON.stringify(sku)} />
                </div>
                <div className="flex gap-2">
                  {sku.anomaly_rows.slice(0, 3).map((r) => (
                    <div key={r.ds} className="text-right">
                      <p className="text-xs text-slate-500">{r.ds}</p>
                      <p className="text-xs font-semibold text-amber-600">score {(r.score * 100).toFixed(0)}%</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

interface RequirementState {
  complete: boolean;
  loading: boolean;
  unavailable: boolean;
  detail: string;
}

function AccuracyReadiness({
  completedRequirements,
  forecast,
  sales,
  quality,
}: {
  completedRequirements: number;
  forecast: RequirementState;
  sales: RequirementState;
  quality: RequirementState;
}) {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-[var(--accent)]">
          <BarChart3 size={14} /> Forecast accuracy
        </div>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-content">Model performance & anomaly log</h1>
        <p className="mt-1 max-w-2xl text-content-subtle">
          Accuracy appears only after a forecast can be compared with actual sales. No score is estimated before then.
        </p>
      </div>

      <Card padding="none" className="overflow-hidden">
        <div className="flex flex-col gap-4 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-content-subtle">Readiness</p>
            <h2 className="mt-1 font-heading text-lg font-semibold text-content">
              {completedRequirements === 3 ? "Inputs are ready; waiting for comparison data" : "Complete the accuracy prerequisites"}
            </h2>
          </div>
          <div className="min-w-[180px]">
            <div className="flex items-center justify-between text-xs font-semibold text-content-muted">
              <span>{completedRequirements} of 3 confirmed</span>
              <span>{Math.round((completedRequirements / 3) * 100)}%</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3" aria-hidden="true">
              <div
                className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-300"
                style={{ width: `${(completedRequirements / 3) * 100}%` }}
              />
            </div>
          </div>
        </div>

        <div className="grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0">
          <Requirement title="Forecast generated" state={forecast} />
          <Requirement title="Actual sales available" state={sales} />
          <Requirement title="Inputs healthy" state={quality} />
        </div>

        <div className="flex flex-wrap gap-2 border-t border-line bg-surface-2 px-5 py-4">
          <Link to="/workspace/forecasts" className="btn-primary px-4 py-2.5 text-sm">
            Open forecasts
          </Link>
          <Link to="/workspace/sales-analytics" className="btn-secondary px-4 py-2.5 text-sm">
            Check sales analytics
          </Link>
          <Link to="/workspace/data-quality" className="btn-ghost px-4 py-2.5 text-sm">
            Review data quality
          </Link>
        </div>
      </Card>
    </div>
  );
}

function Requirement({ title, state }: { title: string; state: RequirementState }) {
  const Icon = state.loading ? Loader2 : state.complete ? CheckCircle2 : Circle;
  const label = state.loading
    ? "Checking"
    : state.unavailable
      ? "Could not verify"
      : state.complete
        ? "Confirmed"
        : "Required";

  return (
    <div className="p-5">
      <div className="flex items-center gap-2">
        <Icon
          size={16}
          className={state.loading ? "animate-spin text-content-subtle" : state.complete ? "text-emerald-600" : "text-amber-600"}
          aria-hidden="true"
        />
        <span className="text-[11px] font-bold uppercase tracking-widest text-content-subtle">{label}</span>
      </div>
      <h3 className="mt-3 font-heading text-sm font-semibold text-content">{title}</h3>
      <p className="mt-1.5 text-xs leading-relaxed text-content-subtle">
        {state.unavailable && !state.loading ? "This check is temporarily unavailable." : state.detail}
      </p>
    </div>
  );
}
