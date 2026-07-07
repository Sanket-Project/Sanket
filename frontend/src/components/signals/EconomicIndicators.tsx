import { Banknote, TrendingUp, TrendingDown, Minus } from "lucide-react";
import clsx from "clsx";
import type { TrendSignal } from "@/types/api";

function strengthLabel(score: number): string {
  const abs = Math.abs(score);
  if (abs < 0.05) return "Neutral";
  const mag = abs >= 0.5 ? "Strong" : abs >= 0.2 ? "Moderate" : "Mild";
  return score > 0 ? `${mag} boost` : `${mag} drag`;
}

interface Props {
  signals: TrendSignal[];
  loading?: boolean;
}

const SERIES_LABEL: Record<string, string> = {
  CPIAUCSL: "Consumer Price Index",
  CPIMEDSL: "Medical CPI",
  PPIACO: "Producer Price Index",
  UNRATE: "Unemployment Rate",
  UMCSENT: "Consumer Sentiment",
  PCE: "Personal Consumption",
  INDPRO: "Industrial Production",
};

export const EconomicIndicators = ({ signals, loading }: Props) => {
  if (loading) {
    return (
      <div className="glass rounded-2xl p-6 animate-pulse">
        <div className="h-5 w-48 bg-white/10 rounded mb-4" />
        <div className="space-y-2">
          <div className="h-10 bg-white/5 rounded" />
          <div className="h-10 bg-white/5 rounded" />
          <div className="h-10 bg-white/5 rounded" />
        </div>
      </div>
    );
  }

  // Group by series_key, take the most recent observation for each
  const latestBySeries = new Map<string, TrendSignal>();
  signals.forEach((s) => {
    const existing = latestBySeries.get(s.series_key);
    if (!existing || new Date(s.captured_at) > new Date(existing.captured_at)) {
      latestBySeries.set(s.series_key, s);
    }
  });

  const rows = Array.from(latestBySeries.values()).sort(
    (a, b) => Math.abs(b.normalized_score) - Math.abs(a.normalized_score),
  );

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-200/70">
      <div className="flex items-center gap-2 mb-4">
        <Banknote size={14} className="text-cyan-300" />
        <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
          Economic Indicators (FRED)
        </h3>
      </div>

      {rows.length === 0 ? (
        <div className="text-sm text-slate-500 py-6 text-center">
          No economic signals yet. Pipeline runs every 15 minutes.
        </div>
      ) : (
        <div className="space-y-2.5">
          {rows.map((s) => {
            const score = Number(s.normalized_score);
            const positive = score >= 0;
            return (
              <div
                key={s.id}
                className="flex items-center gap-3 py-1.5 border-b border-slate-100 last:border-b-0"
              >
                {/* Arrow icon */}
                {(() => {
                  const ArrIcon = score > 0.05 ? TrendingUp : score < -0.05 ? TrendingDown : Minus;
                  const arrColor = score > 0.05 ? "text-emerald-500" : score < -0.05 ? "text-rose-500" : "text-slate-400";
                  const arrBg = score > 0.05 ? "bg-emerald-50" : score < -0.05 ? "bg-rose-50" : "bg-slate-50";
                  return (
                    <div className={clsx("w-7 h-7 rounded-lg flex items-center justify-center shrink-0", arrBg)}>
                      <ArrIcon size={13} className={arrColor} />
                    </div>
                  );
                })()}

                <div className="flex-1 min-w-0">
                  <div className="text-sm text-slate-800 font-medium truncate">
                    {SERIES_LABEL[s.series_key] || s.series_key}
                  </div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                    {s.series_key}
                    {s.payload?.synthetic ? " · synthetic" : ""}
                  </div>
                </div>

                <div className="text-right shrink-0">
                  {s.raw_value !== null && (
                    <div className="text-xs text-slate-500 tabular-nums">
                      {Number(s.raw_value).toFixed(2)}
                    </div>
                  )}
                  <div
                    className={clsx(
                      "text-[11px] font-semibold",
                      positive ? "text-emerald-600" : "text-rose-600",
                    )}
                  >
                    {strengthLabel(score)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
