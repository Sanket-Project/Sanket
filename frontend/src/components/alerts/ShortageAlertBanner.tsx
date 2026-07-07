import { AlertTriangle, AlertOctagon, Info, X } from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import type { ShortageAlert } from "@/types/api";

interface Props {
  alerts: ShortageAlert[];
  onAcknowledge?: (id: string) => void;
  maxVisible?: number;
}

const SEVERITY_STYLE: Record<
  string,
  { container: string; icon: typeof AlertTriangle; iconColor: string; label: string }
> = {
  critical: {
    container: "border-rose-500/40 bg-rose-500/10",
    icon: AlertOctagon,
    iconColor: "text-rose-400",
    label: "Critical",
  },
  warning: {
    container: "border-amber-500/40 bg-amber-500/10",
    icon: AlertTriangle,
    iconColor: "text-amber-400",
    label: "Warning",
  },
  info: {
    container: "border-cyan-500/40 bg-cyan-500/10",
    icon: Info,
    iconColor: "text-cyan-400",
    label: "Info",
  },
};

export const ShortageAlertBanner = ({
  alerts,
  onAcknowledge,
  maxVisible = 3,
}: Props) => {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const visible = alerts
    .filter((a) => !dismissed.has(a.id) && a.status === "open")
    .slice(0, maxVisible);

  if (visible.length === 0) return null;

  return (
    <div className="space-y-2">
      {visible.map((alert) => {
        const style = SEVERITY_STYLE[alert.severity] || SEVERITY_STYLE.info;
        const Icon = style.icon;
        return (
          <div
            key={alert.id}
            className={clsx(
              "rounded-xl border px-4 py-3 flex items-start gap-3 backdrop-blur-md",
              style.container,
            )}
          >
            <Icon size={18} className={clsx("mt-0.5 shrink-0", style.iconColor)} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span
                  className={clsx(
                    "text-[10px] uppercase tracking-wider font-bold",
                    style.iconColor,
                  )}
                >
                  {style.label}
                </span>
                <span className="text-[10px] text-white/40 uppercase tracking-wider">
                  Risk {(alert.risk_score * 100).toFixed(0)}%
                </span>
                {alert.coverage_days !== null && (
                  <span className="text-[10px] text-white/40 uppercase tracking-wider">
                    {alert.coverage_days.toFixed(1)} days cover
                  </span>
                )}
              </div>
              <div className="text-sm font-semibold text-white truncate">
                {alert.title}
              </div>
              <div className="text-xs text-white/65 mt-0.5 line-clamp-2">
                {alert.message}
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {onAcknowledge && (
                <button
                  onClick={() => onAcknowledge(alert.id)}
                  className="text-[11px] px-2 py-1 rounded-md bg-white/10 hover:bg-white/15 text-white/85 transition"
                >
                  Acknowledge
                </button>
              )}
              <button
                onClick={() =>
                  setDismissed((s) => new Set(s).add(alert.id))
                }
                className="text-white/40 hover:text-white/80 transition p-1"
                aria-label="Dismiss"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
