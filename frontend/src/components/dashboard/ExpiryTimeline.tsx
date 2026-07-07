import clsx from "clsx";
import { AlertTriangle, Clock } from "lucide-react";
import { fmtDate, fmtCompact } from "@/utils/format";
import type { PharmaBatchExpiring } from "@/types/api";

interface Props {
  batches: PharmaBatchExpiring[];
  count: number;
}

function daysUntil(date: string) {
  return Math.ceil((new Date(date).getTime() - Date.now()) / 86400_000);
}

export const ExpiryTimeline = ({ batches, count }: Props) => {
  const sorted = [...batches]
    .sort(
      (a, b) =>
        new Date(a.expiry_date).getTime() - new Date(b.expiry_date).getTime()
    )
    .slice(0, 8);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-content-subtle">
          Expiry Timeline
        </p>
        <span className="text-xs font-medium text-content-muted flex items-center gap-1">
          <Clock size={12} />
          {count} batches within 90d
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="text-center py-6 text-sm text-content-subtle">
          No batches expiring within 90 days.
        </div>
      ) : (
        sorted.map((b) => {
          const days = daysUntil(b.expiry_date);
          const isRed = days <= 30;
          const isAmber = days > 30 && days <= 60;
          const urgencyPct = Math.max(0, Math.min(100, ((90 - days) / 90) * 100));

          return (
            <div
              key={b.id}
              className={clsx(
                "relative rounded-xl p-3 border transition-all duration-200 hover:shadow-sm",
                isRed
                  ? "border-rose-200/80 bg-rose-50/60 dark:border-rose-700/40 dark:bg-rose-900/15"
                  : isAmber
                  ? "border-amber-200/80 bg-amber-50/60 dark:border-amber-700/40 dark:bg-amber-900/15"
                  : "border-line bg-surface-2"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    {isRed && (
                      <AlertTriangle
                        size={11}
                        className="text-rose-500 shrink-0"
                      />
                    )}
                    <span className="font-mono text-xs font-semibold text-content truncate">
                      {b.lot_number}
                    </span>
                    {b.ndc_code && (
                      <span className="font-mono text-[11px] text-content-subtle">· {b.ndc_code}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-content-muted tabular-figs">
                    <span>Exp {fmtDate(b.expiry_date)}</span>
                    <span>·</span>
                    <span>{fmtCompact(b.quantity_remaining)} units</span>
                    {b.cold_chain_required && (
                      <>
                        <span>·</span>
                        <span className="text-cyan-600 dark:text-cyan-400 font-semibold">
                          Cold Chain
                        </span>
                      </>
                    )}
                  </div>
                </div>

                <span
                  className={clsx(
                    "shrink-0 font-mono text-[11px] font-semibold px-2 py-0.5 rounded-lg tabular-figs",
                    isRed
                      ? "bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300"
                      : isAmber
                      ? "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300"
                      : "bg-surface-3 text-content-muted"
                  )}
                >
                  {days}d
                </span>
              </div>

              {/* Urgency fill bar */}
              <div className="mt-2 h-1 rounded-full bg-surface-3 overflow-hidden">
                <div
                  className="h-1 rounded-full transition-all duration-700"
                  style={{
                    width: `${urgencyPct}%`,
                    background: isRed
                      ? "#ef4444"
                      : isAmber
                      ? "#f59e0b"
                      : "#10b981",
                  }}
                />
              </div>
            </div>
          );
        })
      )}
    </div>
  );
};
