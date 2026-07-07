import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitBranch, AlertOctagon } from "lucide-react";
import { apiClient } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Spinner";

const INDUSTRY_COLORS: Record<string, string> = {
  fashion: "bg-violet-100 text-violet-700",
  electronics: "bg-cyan-100 text-cyan-700",
  pharma: "bg-emerald-100 text-emerald-700",
  agrocenter: "bg-green-100 text-green-700",
  hardware: "bg-orange-100 text-orange-700",
};

interface Correlation {
  category: string;
  industries: string[];
  industry_count: number;
  alert_count: number;
  avg_risk_score: number;
  by_industry: Record<string, number>;
}

interface CrossIndustryResponse {
  window_days: number;
  total_critical_alerts: number;
  correlated_categories: number;
  correlations: Correlation[];
}

const fetchCrossIndustry = (days: number): Promise<CrossIndustryResponse> =>
  apiClient.get("/alerts/cross-industry", { params: { window_days: days } }).then((r) => r.data);

const INDUSTRIES = ["fashion", "electronics", "pharma", "agrocenter", "hardware"];

export const CrossIndustryCorrelationPage = () => {
  const [windowDays, setWindowDays] = useState(7);

  const { data, isLoading } = useQuery({
    queryKey: ["cross-industry", windowDays],
    queryFn: () => fetchCrossIndustry(windowDays),
  });

  if (isLoading) return <PageLoader />;

  const correlations = data?.correlations ?? [];

  const riskColor = (score: number) => {
    if (score >= 0.75) return "text-red-600 font-bold";
    if (score >= 0.5) return "text-orange-500 font-semibold";
    return "text-slate-600";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
            <GitBranch size={14} /> Cross-Industry Correlation
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Systemic shortage risks</h1>
          <p className="text-slate-500 mt-1">
            Categories with critical alerts spanning 2+ industries — shared supply-chain pressure points
          </p>
        </div>
        <select
          value={windowDays}
          onChange={(e) => setWindowDays(Number(e.target.value))}
          className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white"
        >
          {[3, 7, 14, 30].map((d) => (
            <option key={d} value={d}>{d}-day window</option>
          ))}
        </select>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total Critical Alerts", value: data?.total_critical_alerts ?? 0, color: "text-red-600" },
          { label: "Correlated Categories", value: data?.correlated_categories ?? 0, color: "text-orange-500" },
          { label: "Window (days)", value: windowDays, color: "text-slate-700" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
            <p className="text-xs text-slate-400 uppercase tracking-wide">{label}</p>
            <p className={`text-2xl font-bold mt-1 ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {correlations.length === 0 ? (
        <Card title="No cross-industry correlations found">
          <div className="py-12 text-center">
            <AlertOctagon size={32} className="mx-auto text-slate-300 mb-3" />
            <p className="text-slate-500 text-sm">
              No categories with critical alerts across multiple industries in the last {windowDays} days.
            </p>
            <p className="text-slate-400 text-xs mt-1">Try widening the time window or wait for more alert data.</p>
          </div>
        </Card>
      ) : (
        <>
          {/* Heatmap grid */}
          <Card title="Industry × category heatmap" description="Number of critical alerts per cell">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left py-2 px-3 text-slate-500 font-medium text-xs w-40">Category</th>
                    {INDUSTRIES.map((ind) => (
                      <th key={ind} className="py-2 px-3 text-center">
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${INDUSTRY_COLORS[ind] ?? "bg-slate-100 text-slate-600"}`}>
                          {ind}
                        </span>
                      </th>
                    ))}
                    <th className="py-2 px-3 text-center text-slate-500 font-medium text-xs">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {correlations.slice(0, 15).map((c) => (
                    <tr key={c.category} className="border-b border-slate-50 hover:bg-slate-50/50">
                      <td className="py-2 px-3 font-medium text-slate-700 capitalize">{c.category}</td>
                      {INDUSTRIES.map((ind) => {
                        const count = c.by_industry[ind] ?? 0;
                        return (
                          <td key={ind} className="py-2 px-3 text-center">
                            {count > 0 ? (
                              <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold ${
                                count >= 3 ? "bg-red-100 text-red-700" : count >= 2 ? "bg-orange-100 text-orange-600" : "bg-amber-50 text-amber-600"
                              }`}>
                                {count}
                              </span>
                            ) : (
                              <span className="text-slate-200">—</span>
                            )}
                          </td>
                        );
                      })}
                      <td className={`py-2 px-3 text-center text-sm ${riskColor(c.avg_risk_score)}`}>
                        {(c.avg_risk_score * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Detail cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {correlations.slice(0, 6).map((c) => (
              <div key={c.category} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-semibold text-slate-800 capitalize">{c.category}</p>
                    <p className="text-xs text-slate-400">{c.alert_count} alerts · {c.industry_count} industries</p>
                  </div>
                  <span className={`text-sm font-bold ${riskColor(c.avg_risk_score)}`}>
                    {(c.avg_risk_score * 100).toFixed(0)}% risk
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {c.industries.map((ind) => (
                    <span key={ind} className={`text-xs px-2 py-0.5 rounded-full font-medium ${INDUSTRY_COLORS[ind] ?? "bg-slate-100 text-slate-600"}`}>
                      {ind} ({c.by_industry[ind]})
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
