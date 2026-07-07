import { useQuery } from "@tanstack/react-query";
import { BarChart3, AlertCircle, CheckCircle2 } from "lucide-react";
import { forecastAccuracyApi } from "@/api/forecastAccuracy";
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

  if (isLoading) return <PageLoader />;

  const rows = accuracy?.rows ?? [];

  // Full-page empty state when no accuracy data exists yet
  if (rows.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
            <BarChart3 size={14} /> Forecast Accuracy
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Model performance & anomaly log</h1>
        </div>
        <div className="flex flex-col items-center justify-center min-h-[50vh] text-center space-y-4 p-10 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30">
          <div className="h-16 w-16 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
            <BarChart3 size={28} className="text-slate-400" />
          </div>
          <div className="max-w-sm">
            <h2 className="text-xl font-bold text-slate-700 dark:text-slate-200">No accuracy data yet</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-2 text-sm leading-relaxed">
              Generate a forecast and allow at least one week of actual sales data to accumulate. SANKET will then compute MAPE, WAPE, and anomaly scores automatically.
            </p>
          </div>
        </div>
      </div>
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
          <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
            <BarChart3 size={14} /> Forecast Accuracy
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Model performance & anomaly log</h1>
          <p className="text-slate-500 mt-1">
            MAPE/WAPE per SKU and model · {accuracy?.source === "cached" ? "Pre-computed" : "Live"} computation
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
            <CategoryBar data={modelAvg} accent="#7c3aed" />
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
