import type { ReactNode } from "react";
import type { IndustryCode } from "@/types/api";
import { industryTheme } from "@/utils/colors";

interface Props {
  industry: IndustryCode;
  label: string;
  title: string;
  subtitle: string;
  icon: ReactNode;
  horizonWeeks: number;
  models: string[];
  healthScore?: number; // 0–100
  extraBadge?: ReactNode;
}

function HealthRing({ score, color }: { score: number; color: string }) {
  const r = 22;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: 64, height: 64 }}>
        <svg width={64} height={64} viewBox="0 0 64 64">
          <circle cx={32} cy={32} r={r} fill="none" stroke="currentColor" className="text-line" strokeWidth={5} />
          <circle
            cx={32}
            cy={32}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={5}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circ}`}
            strokeDashoffset={circ * 0.25}
            style={{ transition: "stroke-dasharray 1.2s cubic-bezier(0.34,1.56,0.64,1)" }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <span className="font-mono text-sm font-semibold text-content tabular-figs">{score}%</span>
        </div>
      </div>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-content-subtle">Health</span>
    </div>
  );
}

export const IndustryHero = ({
  industry,
  label,
  title,
  subtitle,
  icon,
  horizonWeeks,
  models,
  healthScore = 82,
  extraBadge,
}: Props) => {
  const theme = industryTheme(industry);

  return (
    <div className="relative rounded-2xl overflow-hidden bg-surface border border-line shadow-sm p-6">
      {/* Accent top bar */}
      <div className="absolute top-0 left-0 right-0 h-1" style={{ background: theme.gradient }} />

      <div className="relative flex items-center justify-between gap-6">
        {/* Left: icon + text */}
        <div className="flex items-center gap-5 min-w-0">
          <div
            className="h-14 w-14 rounded-2xl grid place-items-center text-white shrink-0 shadow-sm"
            style={{ background: theme.gradient }}
          >
            <span className="scale-125">{icon}</span>
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: theme.accent }}>
              {label}
            </div>
            <h1 className="font-heading text-2xl font-semibold tracking-tight text-content leading-tight">
              {title}
            </h1>
            <p className="text-sm text-content-muted mt-1">{subtitle}</p>
          </div>
        </div>

        {/* Right: model badges + health */}
        <div className="flex items-center gap-6 shrink-0">
          <div className="hidden md:flex flex-col gap-2 items-end">
            <div className="flex flex-wrap gap-1.5 justify-end max-w-56">
              {models.slice(0, 4).map((m) => (
                <span
                  key={m}
                  className="px-2.5 py-0.5 rounded-full text-[11px] font-medium border"
                  style={{
                    color: theme.accent,
                    borderColor: "var(--border)",
                    background: "var(--accent-soft)",
                  }}
                >
                  {m}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-3 text-xs text-content-muted">
              <span className="flex items-center gap-1.5 tabular-figs">
                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: theme.accent }} />
                {horizonWeeks}w horizon
              </span>
              {extraBadge}
            </div>
          </div>
          <HealthRing score={healthScore} color={theme.accent} />
        </div>
      </div>
    </div>
  );
};
