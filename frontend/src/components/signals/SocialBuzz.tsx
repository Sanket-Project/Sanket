import { MessageSquare, TrendingUp, TrendingDown, Minus } from "lucide-react";
import clsx from "clsx";
import type { TrendSignal } from "@/types/api";

function strengthLabel(score: number): string {
  const abs = Math.abs(score);
  if (abs < 0.05) return "Neutral";
  const mag = abs >= 0.5 ? "Strong" : abs >= 0.2 ? "Moderate" : "Mild";
  return score > 0 ? `${mag} buzz` : `${mag} decline`;
}

interface Props {
  signals: TrendSignal[];
  loading?: boolean;
}

export const SocialBuzz = ({ signals, loading }: Props) => {
  if (loading) {
    return (
      <div className="glass rounded-2xl p-6 animate-pulse">
        <div className="h-5 w-32 bg-white/10 rounded mb-4" />
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-10 bg-white/5 rounded" />
          ))}
        </div>
      </div>
    );
  }

  // Latest sample per series
  const latestBySeries = new Map<string, TrendSignal>();
  signals.forEach((s) => {
    const existing = latestBySeries.get(s.series_key);
    if (!existing || new Date(s.captured_at) > new Date(existing.captured_at)) {
      latestBySeries.set(s.series_key, s);
    }
  });
  const rows = Array.from(latestBySeries.values()).sort(
    (a, b) => Number(b.normalized_score) - Number(a.normalized_score),
  );

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-200/70">
      <div className="flex items-center gap-2 mb-4">
        <MessageSquare size={14} className="text-violet-300" />
        <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
          Social & Search
        </h3>
      </div>

      {rows.length === 0 ? (
        <div className="text-sm text-slate-500 py-6 text-center">
          No social/search signals yet.
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((s) => {
            const score = Number(s.normalized_score);
            const isUp = score > 0.05;
            const isDown = score < -0.05;
            const ArrIcon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
            const arrColor = isUp ? "text-emerald-500" : isDown ? "text-rose-500" : "text-slate-400";
            const arrBg = isUp ? "bg-emerald-50" : isDown ? "bg-rose-50" : "bg-slate-50";
            const label = s.series_key
              .replace(/^google:/, "")
              .replace(/^reddit:r\//, "r/")
              .replace(/^reddit:/, "")
              .replace(/_/g, " ")
              .replace(/\b\w/g, (c) => c.toUpperCase());
            const sourceTag = s.series_key.startsWith("google:")
              ? "Google"
              : s.series_key.startsWith("reddit:")
              ? "Reddit"
              : s.source.replace(/_/g, " ");
            return (
              <li
                key={s.id}
                className="flex items-center gap-2.5 py-1.5 border-b border-slate-100 last:border-b-0"
              >
                <div className={clsx("w-7 h-7 rounded-lg flex items-center justify-center shrink-0", arrBg)}>
                  <ArrIcon size={13} className={arrColor} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-slate-800 font-medium truncate">{label}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">{sourceTag}</div>
                </div>
                <span className={clsx("text-[11px] font-semibold shrink-0", arrColor)}>
                  {strengthLabel(score)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
