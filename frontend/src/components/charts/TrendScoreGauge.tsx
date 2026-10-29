import { TrendingUp, TrendingDown, Minus, Activity } from "@/components/ui/icons";
import type { TrendScore, IndustryCode } from "@/types/api";
const INDUSTRY_CONFIG = Object.fromEntries(["fashion", "electronics", "pharma", "hardware", "agrocenter"].map((key) => [key, { accent: "text-accent", icon: <Activity size={18} /> }]));
function scoreToPercent(score: number) {
  // score is -1..+1, map to 0..100
  return Math.round(((score + 1) / 2) * 100);
}

function verdict(score: number) {
  if (score >= 0.25) return { text: "Demand is strongly heating up", sub: "Multiple signals confirm a significant demand surge", tone: "up" };
  if (score >= 0.08) return { text: "Demand is ticking upward", sub: "Positive momentum across most signal sources", tone: "up" };
  if (score >= -0.08) return { text: "Demand looks stable", sub: "Signals are mixed — no strong directional pull", tone: "flat" };
  if (score >= -0.25) return { text: "Demand is softening slightly", sub: "Watch for further cooling in the coming weeks", tone: "down" };
  return { text: "Demand is cooling down", sub: "Multiple signals point to a meaningful demand dip", tone: "down" };
}

export function TrendScoreGauge({ score, loading, industry }: { score: TrendScore | undefined; loading: boolean; industry: IndustryCode }) {
  const cfg = INDUSTRY_CONFIG[industry];
  const data = score ?? {
    industry,
    score: 0,
    volatility: 0,
    sample_count: 0,
    drivers: [],
    demand_factors: [],
    horizon_days: 90,
    by_kind: {},
    as_of: new Date().toISOString()
  };
  const ev = score?.evidence;
  // Only enough fresh evidence supports a direction or an agreement figure.
  // Zero samples once read as "stable demand, High (100%) agreement".
  const ready = Boolean(score) && (ev ? ev.agreement_reportable : score?.volatility != null);
  const pct = ready ? scoreToPercent(data.score) : 50;
  const v = ready
    ? verdict(data.score)
    : !score
      ? { text: "Signal score unavailable", sub: "The trend score could not be loaded.", tone: "flat" }
      : {
          text:
            ev?.status === "unavailable"
              ? "No signal evidence"
              : ev?.status === "stale"
                ? "Signals are stale"
                : "Insufficient signal evidence",
          sub: ev?.message || "Too few signal samples to say which way demand is moving.",
          tone: "flat",
        };
  const agreement = ready && data.volatility != null ? Math.round((1 - data.volatility) * 100) : null;
  const sampleCount = data.sample_count;
  const needs = ev && sampleCount < ev.min_samples ? ` (needs ${ev.min_samples})` : "";

  const STROKE = 10;
  const R = 54;
  const CIRC = 2 * Math.PI * R;
  const dash = (pct / 100) * CIRC;

  const dirColor =
    v.tone === "up" ? "#10b981" : v.tone === "down" ? "#ef4444" : "#94a3b8";
  const DirIcon = v.tone === "up" ? TrendingUp : v.tone === "down" ? TrendingDown : Minus;

  return (
    <div className="rounded-2xl border border-line bg-surface p-5 relative overflow-hidden">

      <div className="flex items-center gap-2 mb-5">
        <span className={cfg.accent}>{cfg.icon}</span>
        <h3 className="text-sm font-bold text-content dark:text-content tracking-tight">
          Overall Demand Trend
        </h3>
        {loading && (
          <span className="ml-auto text-[10px] text-amber-600 dark:text-amber-400 font-semibold animate-pulse">
            Syncing…
          </span>
        )}
      </div>

      {/* Gauge ring */}
      <div className="flex items-center gap-5">
        <div className="relative shrink-0" style={{ width: 128, height: 128 }}>
          <svg width={128} height={128} viewBox="0 0 128 128">
            {/* Track */}
            <circle cx={64} cy={64} r={R} fill="none" stroke="var(--border)" strokeWidth={STROKE}  />
            {/* Fill */}
            <circle
              cx={64} cy={64} r={R}
              fill="none"
              stroke={dirColor}
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${dash} ${CIRC}`}
              strokeDashoffset={CIRC * 0.25}
              style={{ transition: "stroke-dasharray 500ms ease" }}
            />
          </svg>
          {/* Center value */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <DirIcon size={16} style={{ color: dirColor }} />
            <span className="text-2xl font-semibold tabular-nums" style={{ color: dirColor }}>
              {ready ? `${data.score >= 0 ? "+" : ""}${Math.round(data.score * 100)}` : "—"}
            </span>
            <span className="text-[9px] text-content-subtle dark:text-content-muted font-semibold uppercase tracking-wider">score</span>
          </div>
        </div>

        <div className="flex-1 min-w-0 space-y-3">
          <div>
            <p className="text-base font-bold text-content dark:text-content leading-snug">{v.text}</p>
            <p className="text-xs text-content-muted dark:text-content-subtle mt-0.5">{v.sub}</p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span className="text-content-muted dark:text-content-subtle">
                {`${sampleCount.toLocaleString()} sample${sampleCount === 1 ? "" : "s"}${needs}`}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="text-content-muted dark:text-content-subtle">{data.horizon_days}d horizon</span>
            </div>
          </div>
        </div>
      </div>

      {/* Agreement bar — only when there is evidence to measure it */}
      {agreement == null ? (
        <p className="mt-5 text-[10px] text-content-subtle dark:text-content-muted">
          Signal agreement is not shown: there is not enough recent signal evidence to measure it.
        </p>
      ) : (
      <div className="mt-5">
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-content-subtle dark:text-content-muted mb-1.5">
          <span>Signal agreement</span>
          <span className={agreement >= 70 ? "text-emerald-600 dark:text-emerald-400" : agreement >= 50 ? "text-amber-600 dark:text-amber-400" : "text-rose-500 dark:text-rose-400"}>
            {agreement >= 70 ? "High" : agreement >= 50 ? "Moderate" : "Low"} ({agreement}%)
          </span>
        </div>
        <div className="h-2 rounded-full bg-surface-2 dark:bg-surface-2/60 overflow-hidden">
          <div
            className="h-2 rounded-full bg-[var(--accent)] transition-all duration-500"
            style={{ width: `${agreement}%` }}
          />
        </div>
        <p className="text-[10px] text-content-subtle dark:text-content-muted mt-1">
          {agreement >= 70 ? "Sources are largely aligned — high confidence" : agreement >= 50 ? "Mixed signals — treat forecasts as directional" : "Sources conflict — treat as rough estimate"}
        </p>
      </div>
      )}
    </div>
  );
}

