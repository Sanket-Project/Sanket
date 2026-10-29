import clsx from "clsx";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "@/components/ui/icons";

export type Provenance = "recorded" | "estimated" | "forecast" | "heuristic";

const PROVENANCE_LABEL: Record<Provenance, string> = {
  recorded: "Recorded", estimated: "Estimated", forecast: "Forecast", heuristic: "Heuristic",
};
// Recorded is solid; derived values are outlined so the difference survives greyscale.
const PROVENANCE_CLS: Record<Provenance, string> = {
  recorded: "bg-surface-3 text-content-muted",
  estimated: "border border-dashed border-line-strong text-content-muted",
  forecast: "border border-dashed border-accent/40 text-accent",
  heuristic: "border border-dashed border-amber-500/50 text-amber-700 dark:text-amber-300",
};
const TONE_ICON = {
  default: "bg-accent-soft text-accent",
  success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  warning: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  danger: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
};
const TONE_DOT = { success: "bg-emerald-500", warning: "bg-amber-500", danger: "bg-rose-500" };

interface Props {
  label: string;
  value: ReactNode | null | undefined;
  unit?: string;
  provenance: Provenance;
  hint?: ReactNode;
  tone?: keyof typeof TONE_ICON;
  icon?: ReactNode;
  href?: string;
  onClick?: () => void;
  unavailableReason?: string;
  className?: string;
}

export const MetricTile = ({ label, value, unit, provenance, hint, tone = "default", icon, href, onClick, unavailableReason, className }: Props) => {
  const missing = value === null || value === undefined;
  const interactive = Boolean(href || onClick);
  const body = (
    <>
      <div className="flex items-start gap-3">
        {icon && <div className={clsx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", TONE_ICON[tone])}>{icon}</div>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {tone !== "default" && !icon && <span aria-hidden="true" className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", TONE_DOT[tone])} />}
            <span className="t-label">{label}</span>
            <span className={clsx("rounded px-1.5 py-px text-[10px] font-medium", PROVENANCE_CLS[provenance])}>{PROVENANCE_LABEL[provenance]}</span>
          </div>
          <p className="mt-1.5 flex items-baseline gap-1.5">
            <span className="t-kpi">{missing ? "—" : value}</span>
            {!missing && unit && <span className="t-label">{unit}</span>}
          </p>
          {missing
            ? <p className="mt-1 text-xs text-content-subtle">{unavailableReason ?? "Not available from current data"}</p>
            : hint && <p className="mt-1 text-xs text-content-subtle">{hint}</p>}
        </div>
        {interactive && <ChevronRight size={16} aria-hidden="true" className="mt-1 shrink-0 text-content-subtle transition-transform duration-fast ease-standard group-hover:translate-x-0.5" />}
      </div>
    </>
  );
  const cls = clsx("group block min-w-0 rounded-2xl border border-line bg-surface p-4 text-left shadow-sm", interactive && "focus-ring transition-colors duration-fast ease-standard hover:border-line-strong", className);
  if (href) return <Link to={href} className={cls}>{body}</Link>;
  if (onClick) return <button type="button" onClick={onClick} className={clsx(cls, "w-full")}>{body}</button>;
  return <div className={cls}>{body}</div>;
};
