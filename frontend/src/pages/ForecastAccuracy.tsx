import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart3, AlertCircle, CheckCircle2, Circle, Loader2 } from "@/components/ui/icons";
import { forecastAccuracyApi } from "@/api/forecastAccuracy";
import { forecastConfidenceApi } from "@/api/forecasts";
import { salesAnalyticsApi } from "@/api/salesAnalytics";
import { dataQualityApi } from "@/api/dataQuality";
import { Card } from "@/components/ui/Card";
import { CategoryBar } from "@/components/charts/CategoryBar";
import { PageLoader } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { useIndustryStore } from "@/stores/industry";

const mapeColor = (mape: number | null) => {
  if (mape === null) return "text-slate-400";
  if (mape < 10) return "text-emerald-600";
  if (mape < 25) return "text-amber-500";
  return "text-red-500";
};

const mapeLabel = (mape: number | null) => {
  if (mape === null) return "—";
  if (mape < 10) return "Excellent";
  if (mape < 25) return "Good";
  return "Needs work";
};

export const ForecastAccuracyPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);

  const { data: accuracy, isLoading } = useQuery({
    queryKey: ["forecast-accuracy", industry],
    queryFn: () => forecastAccuracyApi.list(100),
  });

  const { data: anomalies } = useQuery({
    queryKey: ["anomalies", industry],
    queryFn: () => forecastAccuracyApi.anomalies(90),
  });

  const hasAccuracyRows = (accuracy?.rows.length ?? 0) > 0;
  const readinessEnabled = !isLoading && !hasAccuracyRows;

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

  const rows = accuracy?.rows ?? [];

  if (rows.length === 0) {
    const hasForecastRun = Boolean(confidence?.run_id);
    const hasSalesHistory = (salesHistory?.series.length ?? 0) > 0;
    const hasHealthyInputs = Boolean(quality && quality.critical === 0);
    const completedRequirements = [hasForecastRun, hasSalesHistory, hasHealthyInputs].filter(Boolean).length;

    return (
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
    );
  }

  // Aggregate MAPE by model for bar chart
  const byModel: Record<string, number[]> = {};
  for (const row of rows) {
    if (row.mape !== null) {
      (byModel[row.model_name] ??= []).push(row.mape);
    }
  }
  const modelAvg = Object.entries(byModel).map(([model, mapes]) => ({
    category: model,
    count: Math.round(mapes.reduce((a, b) => a + b, 0) / mapes.length),
  })).sort((a, b) => a.count - b.count);

  const overallMape = rows.length > 0 && rows.some((r) => r.mape !== null)
    ? rows.filter((r) => r.mape !== null).reduce((s, r) => s + r.mape!, 0) / rows.filter((r) => r.mape !== null).length
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-[var(--accent)] text-sm font-medium uppercase tracking-wider">
            <BarChart3 size={14} /> Forecast Accuracy
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Model performance & anomaly log</h1>
          <p className="text-slate-500 mt-1">
            Forecast error by SKU and model · {accuracy?.source === "cached" ? "Pre-computed" : "Live"} calculation
          </p>
        </div>
        {overallMape !== null && (
          <div className="text-right">
            <p className="text-xs text-slate-400 uppercase tracking-wide">Overall MAPE</p>
            <p className={`text-2xl font-bold ${mapeColor(overallMape)}`}>{overallMape.toFixed(1)}%</p>
            <p className={`text-xs ${mapeColor(overallMape)}`}>{mapeLabel(overallMape)}</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Model MAPE bar chart */}
        <Card title="Avg MAPE by model" description="Lower is better — target < 10%">
          {modelAvg.length > 0 ? (
            <CategoryBar data={modelAvg} accent="var(--accent)" />
          ) : (
            <p className="text-slate-400 text-sm py-8 text-center">No accuracy data yet — run a forecast first</p>
          )}
        </Card>

        {/* Accuracy table */}
        <Card className="lg:col-span-2" title="Per-SKU accuracy" description="Sorted by MAPE ascending">
          {rows.length === 0 ? (
            <div className="py-12 text-center">
              <BarChart3 size={32} className="mx-auto text-slate-200 mb-3" />
              <p className="text-slate-400 text-sm">No forecast vs. actuals data available yet.</p>
              <p className="text-slate-300 text-xs mt-1">Generate a forecast and allow a week of actuals to accumulate.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    {["SKU", "Model", "MAPE", "WAPE", "Obs", "Quality"].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-slate-500 font-medium text-xs">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 30).map((row, i) => (
                    <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                      <td className="py-2 px-3 font-mono text-xs text-slate-600">{row.sku_id.slice(0, 8)}…</td>
                      <td className="py-2 px-3"><Badge>{row.model_name}</Badge></td>
                      <td className={`py-2 px-3 font-semibold ${mapeColor(row.mape)}`}>
                        {row.mape !== null ? `${row.mape.toFixed(1)}%` : "—"}
                      </td>
                      <td className="py-2 px-3 text-slate-500">
                        {row.wape !== null ? `${row.wape.toFixed(1)}%` : "—"}
                      </td>
                      <td className="py-2 px-3 text-slate-500">{row.n_obs}</td>
                      <td className="py-2 px-3">
                        {row.mape !== null && row.mape < 10 ? (
                          <CheckCircle2 size={14} className="text-emerald-500" />
                        ) : (
                          <AlertCircle size={14} className="text-amber-400" />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Anomaly log */}
      {anomalies && anomalies.sku_count > 0 && (
        <Card title={`Demand anomalies — ${anomalies.sku_count} SKUs flagged`} description={`Last ${anomalies.window_days} days · STL + Isolation Forest`}>
          <div className="space-y-3">
            {anomalies.anomalous_skus.slice(0, 10).map((sku) => (
              <div key={sku.sku_id} className="flex items-center justify-between border border-amber-100 bg-amber-50/50 rounded-lg px-4 py-3">
                <div>
                  <p className="text-sm font-mono text-slate-700">{sku.sku_id.slice(0, 8)}…</p>
                  <p className="text-xs text-slate-400">{sku.anomaly_count} anomalous weeks · last {sku.latest_anomaly_date}</p>
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
