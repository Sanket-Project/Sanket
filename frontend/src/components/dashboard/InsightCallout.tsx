import type { ReactNode, CSSProperties } from "react";
import clsx from "clsx";
import { ArrowRight, Zap } from "lucide-react";

interface Props {
  insight: string;
  confidence: number; // 0–100
  category?: string;
  ctaLabel?: string;
  onCta?: () => void;
  tone?: "info" | "warning" | "success" | "danger";
  icon?: ReactNode;
}

// Semantic tones use fixed colors; "info" follows the active industry accent.
const TONES: Record<
  NonNullable<Props["tone"]>,
  { wrap: string; badge: string; iconWrap: string; cta: string; useAccent?: boolean }
> = {
  info: {
    wrap: "border-line bg-surface/80 backdrop-blur-md",
    badge: "text-[var(--accent)]",
    iconWrap: "bg-[var(--accent-soft)] text-[var(--accent)] border border-[var(--accent-ring)]",
    cta: "",
    useAccent: true,
  },
  warning: {
    wrap: "border-amber-500/20 bg-amber-50/50 dark:border-amber-500/10 dark:bg-amber-950/10 backdrop-blur-md",
    badge: "text-amber-700 dark:text-amber-400",
    iconWrap: "bg-amber-100 text-amber-700 border border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400",
    cta: "bg-amber-500 hover:bg-amber-600",
  },
  success: {
    wrap: "border-emerald-500/15 bg-emerald-50/50 dark:border-emerald-500/10 dark:bg-emerald-950/10 backdrop-blur-md",
    badge: "text-emerald-700 dark:text-emerald-400",
    iconWrap: "bg-emerald-100/60 text-emerald-700 border border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400",
    cta: "bg-emerald-600 hover:bg-emerald-700",
  },
  danger: {
    wrap: "border-rose-500/20 bg-rose-50/50 dark:border-rose-500/10 dark:bg-rose-950/10 backdrop-blur-md",
    badge: "text-rose-700 dark:text-rose-400",
    iconWrap: "bg-rose-100 text-rose-700 border border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-400",
    cta: "bg-rose-600 hover:bg-rose-700",
  },
};

export const InsightCallout = ({
  insight,
  confidence,
  category,
  ctaLabel = "View Details",
  onCta,
  tone = "info",
  icon,
}: Props) => {
  const t = TONES[tone];
  const accentStyle: CSSProperties | undefined = t.useAccent
    ? { background: "var(--accent-soft)", color: "var(--accent)", borderColor: "var(--accent-ring)" }
    : undefined;

  return (
    <div className={clsx("rounded-[20px] border p-6 flex flex-col sm:flex-row items-start sm:items-center gap-5 shadow-sm", t.wrap)}>
      {/* Icon */}
      <div
        className={clsx("shrink-0 h-11 w-11 rounded-2xl grid place-items-center shadow-sm", t.iconWrap)}
        style={accentStyle}
      >
        {icon ?? <Zap size={18} />}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {(category || confidence) && (
          <div className="flex items-center gap-2 mb-2">
            <span
              className={clsx(
                "text-[10px] font-bold uppercase tracking-widest",
                t.badge,
              )}
            >
              {category || "AI INSIGHT"}
            </span>
            {confidence && (
              <>
                <span className="text-content-subtle/50 text-[10px] font-bold">·</span>
                <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                  {confidence}% confidence
                </span>
              </>
            )}
          </div>
        )}
        <p className="text-sm font-medium text-content leading-relaxed">{insight}</p>
      </div>

      {/* CTA */}
      {onCta && (
        <button
          onClick={onCta}
          className={clsx(
            "shrink-0 inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-white transition-all duration-200 active:scale-95 shadow-sm",
            !t.useAccent ? t.cta : "bg-[var(--accent)] hover:bg-[var(--accent-strong)]",
          )}
        >
          {ctaLabel}
          <ArrowRight size={13} />
        </button>
      )}
    </div>
  );
};
