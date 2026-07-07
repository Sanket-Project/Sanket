import clsx from "clsx";
import { memo, type ReactNode } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";

interface Props {
  label: string;
  value: ReactNode;
  delta?: number; // fractional e.g. 0.063 = +6.3%
  icon?: ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
  subtitle?: string;
  sparkPoints?: number[]; // data points for mini sparkline
}

// Tone → status dot
const TONE_DOT = {
  default: "bg-slate-300 dark:bg-slate-600",
  warning: "bg-amber-500",
  danger: "bg-rose-500",
  success: "bg-emerald-500",
};

// Build an SVG polyline path from a list of values
function buildSparkPath(pts: number[]): string {
  if (pts.length < 2) return "";
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const range = max - min || 1;
  const w = 100;
  const h = 28;
  const pad = 2;
  const coords = pts.map((v, i) => {
    const x = pad + (i / (pts.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x},${y}`;
  });
  return `M${coords.join(" L")}`;
}

export const KPICard = memo(function KPICard({
  label,
  value,
  delta,
  icon,
  tone = "default",
  subtitle,
  sparkPoints,
}: Props) {
  const sparkColor = "var(--accent)";
  const sparkPath = sparkPoints ? buildSparkPath(sparkPoints) : null;
  const gid = `spark-${label.replace(/\W/g, "")}`;

  return (
    <div className="relative rounded-[20px] bg-surface border border-line p-6 shadow-sm transition-all duration-200 ease-out hover:shadow-md hover:border-line-strong">
      {/* Header row */}
      <div className="flex items-center justify-between mb-3.5">
        <span className="text-[10px] font-bold uppercase tracking-widest text-content-subtle">
          {label}
        </span>
        <div className="flex items-center gap-2">
          <span className={clsx("h-1.5 w-1.5 rounded-full shrink-0", TONE_DOT[tone])} />
          {icon && <div className="text-content-subtle/70">{icon}</div>}
        </div>
      </div>

      {/* Value */}
      <div className="font-heading text-[28px] font-semibold text-content tracking-tight leading-none">
        {value}
      </div>

      {subtitle && (
        <p className="text-[11px] text-content-subtle mt-2 font-medium leading-relaxed">{subtitle}</p>
      )}

      {/* Footer: delta + sparkline */}
      <div className="flex items-end justify-between gap-3 mt-3">
        {delta != null ? (
          <div
            className={clsx(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-semibold tabular-figs",
              delta >= 0
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-rose-600 dark:text-rose-400",
            )}
          >
            {delta >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
            {delta >= 0 ? "+" : ""}
            {(delta * 100).toFixed(1)}%
          </div>
        ) : (
          <span />
        )}

        {sparkPath && (
          <div className="h-7 w-24 shrink-0">
            <svg viewBox="0 0 100 28" className="w-full h-full" preserveAspectRatio="none">
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={sparkColor} stopOpacity={0.22} />
                  <stop offset="100%" stopColor={sparkColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <path d={`${sparkPath} L100,28 L0,28 Z`} fill={`url(#${gid})`} />
              <path
                d={sparkPath}
                fill="none"
                stroke={sparkColor}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="animate-draw-line"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          </div>
        )}
      </div>
    </div>
  );
});
