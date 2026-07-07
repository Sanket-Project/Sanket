import { memo } from "react";
import clsx from "clsx";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

interface CategoryItem {
  category: string;
  count: number;
  trend?: "up" | "down" | "flat";
  share?: number; // 0–100
}

interface Props {
  data: CategoryItem[];
  /** Accent color (hex or CSS var). Defaults to the active industry accent. */
  accent?: string;
  title?: string;
}

function computeShares(data: CategoryItem[]): CategoryItem[] {
  const total = data.reduce((s, d) => s + d.count, 0) || 1;
  return data.map((d) => ({ ...d, share: Math.round((d.count / total) * 100) }));
}

export const RankedCategories = memo(function RankedCategories({ data, accent = "var(--accent)", title }: Props) {
  if (!data.length) {
    return <div className="text-center text-content-subtle py-8 text-sm">No category data yet.</div>;
  }

  const sorted = [...computeShares(data)].sort((a, b) => b.count - a.count).slice(0, 7);
  const max = sorted[0]?.count || 1;

  return (
    <div className="space-y-3">
      {title && (
        <p className="text-[11px] font-semibold uppercase tracking-wider text-content-subtle mb-3">{title}</p>
      )}
      {sorted.map((item, i) => {
        const pct = (item.count / max) * 100;
        // First rank full accent; subsequent ranks fade for a clean tiered look.
        const barOpacity = Math.max(0.35, 1 - i * 0.12);

        return (
          <div key={item.category} className="group">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="font-mono text-[11px] font-semibold w-4 text-right shrink-0"
                  style={{ color: accent, opacity: barOpacity }}
                >
                  {i + 1}
                </span>
                <span className="text-[13px] font-medium text-content truncate">{item.category}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-2">
                {item.trend && (
                  <span
                    className={clsx(
                      item.trend === "up"
                        ? "text-emerald-600 dark:text-emerald-400"
                        : item.trend === "down"
                        ? "text-rose-500 dark:text-rose-400"
                        : "text-content-subtle",
                    )}
                  >
                    {item.trend === "up" ? (
                      <TrendingUp size={13} />
                    ) : item.trend === "down" ? (
                      <TrendingDown size={13} />
                    ) : (
                      <Minus size={13} />
                    )}
                  </span>
                )}
                <span className="text-xs font-semibold text-content-muted tabular-figs w-9 text-right">
                  {item.share}%
                </span>
              </div>
            </div>

            <div className="h-2 rounded-full bg-surface-3 overflow-hidden">
              <div
                className="h-2 rounded-full animate-bar-grow"
                style={{ width: `${pct}%`, background: accent, opacity: barOpacity, animationDelay: `${i * 60}ms` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
});
