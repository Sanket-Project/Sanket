import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Info,
  Minus,
  Sparkles,
} from "@/components/ui/icons";
import clsx from "clsx";
import type { ForecastExplanationDriver, HybridForecast } from "@/types/api";

interface Props {
  explanation: HybridForecast["explanation"];
  sampleCount: number;
  dataSource: string;
}

const KIND_LABELS: Record<string, string> = {
  economic_indicator: "Economic conditions",
  social_buzz: "Social interest",
  search_interest: "Search demand",
  news_sentiment: "Industry news",
  commodity_price: "Pricing pressure",
  other: "Other recent signals",
};

const FRED_LABELS: Record<string, string> = {
  CPIAUCSL: "Consumer price trend",
  CPILFESL: "Core inflation trend",
  PCE: "Consumer spending",
  UNRATE: "Employment conditions",
  FEDFUNDS: "Interest-rate environment",
};

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

function explanationDriverLabel(driver: ForecastExplanationDriver): string {
  const key = driver.series_key;
  const lower = key.toLowerCase();
  if (lower === "other:signals") return "Other recent signals";
  if (lower.startsWith("weather:")) {
    const [, location = "local", measure = "weather"] = key.split(":");
    const metric = measure.includes("temp") ? "temperature outlook" : "weather outlook";
    return `${titleCase(location)} ${metric}`;
  }
  if (lower.startsWith("logistics:")) {
    return `${titleCase(key.split(":")[1] ?? "Logistics")} transit conditions`;
  }
  if (lower.startsWith("competitor:")) {
    return `${titleCase(key.split(":").at(-1) ?? "Competitor")} competitor pricing`;
  }
  if (lower.startsWith("google:")) {
    return `${titleCase(key.slice("google:".length))} search demand`;
  }
  if (lower.startsWith("reddit:r/")) {
    return `${titleCase(key.slice("reddit:r/".length))} community interest`;
  }
  if (/^(pinterest|tiktok|instagram):/.test(lower)) {
    return `${titleCase(key.split(":").slice(1).join(" "))} social interest`;
  }
  if (lower.startsWith("rss:") || lower.startsWith("fda:") || lower.startsWith("cdsco:")) {
    return KIND_LABELS[driver.kind] ?? "Industry news";
  }
  return FRED_LABELS[key] ?? titleCase(key) ?? KIND_LABELS[driver.kind] ?? "Demand signal";
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    google_trends: "Google Trends",
    competitor_price: "Competitor data",
    news_api: "News",
    multiple: "Multiple sources",
  };
  return labels[source] ?? titleCase(source);
}

function signedPercent(value: number): string {
  const percentage = value * 100;
  const precision = Math.abs(percentage) < 0.1 && percentage !== 0 ? 2 : 1;
  return `${percentage > 0 ? "+" : ""}${percentage.toFixed(precision)}%`;
}

function signedPoints(value: number): string {
  const points = value * 100;
  const precision = Math.abs(points) < 0.1 && points !== 0 ? 2 : 1;
  return `${points > 0 ? "+" : ""}${points.toFixed(precision)} pp`;
}

export const ForecastChangeExplanation = ({
  explanation,
  sampleCount,
  dataSource,
}: Props) => {
  const shift = explanation.median_shift_pct;
  const direction = shift > 0.0005 ? "up" : shift < -0.0005 ? "down" : "flat";
  const DirectionIcon = direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;
  const drivers = explanation.drivers ?? [];
  const maxImpact = Math.max(...drivers.map((driver) => Math.abs(driver.contribution_pct)), 0.001);
  const bandChange = explanation.band_change_pct;

  return (
    <section
      aria-labelledby="forecast-change-title"
      className="glass rounded-3xl border border-violet-200/60 dark:border-violet-900/50 overflow-hidden shadow-lg shadow-violet-100/40 dark:shadow-none animate-fade-in"
    >
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.45fr)]">
        <div className="p-6 lg:p-7 bg-gradient-to-br from-violet-50/80 via-white/30 to-transparent dark:from-violet-950/25 dark:via-slate-950/10 border-b lg:border-b-0 lg:border-r border-violet-100/80 dark:border-violet-900/40">
          <div className="flex items-center gap-2 text-violet-600 dark:text-violet-400">
            <Sparkles size={15} aria-hidden="true" />
            <h2 id="forecast-change-title" className="text-xs font-extrabold uppercase tracking-[0.16em]">
              Why did the forecast change?
            </h2>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <span
              className={clsx(
                "h-11 w-11 rounded-2xl flex items-center justify-center shrink-0",
                direction === "up" && "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/35 dark:text-emerald-300",
                direction === "down" && "bg-rose-100 text-rose-700 dark:bg-rose-900/35 dark:text-rose-300",
                direction === "flat" && "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
              )}
            >
              <DirectionIcon size={21} aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                Demand expected to {direction === "up" ? "increase" : direction === "down" ? "decrease" : "stay broadly unchanged"}
              </p>
              <p
                className={clsx(
                  "text-4xl font-black tracking-tight tabular-nums",
                  direction === "up" && "text-emerald-700 dark:text-emerald-300",
                  direction === "down" && "text-rose-700 dark:text-rose-300",
                  direction === "flat" && "text-slate-800 dark:text-slate-100",
                )}
              >
                {signedPercent(shift)}
              </p>
            </div>
          </div>

          <p className="mt-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            Compared with the historical model baseline. Driver impacts are additive, so the rows reconcile to the net change above.
          </p>

          <div className="mt-5 pt-4 border-t border-violet-100/80 dark:border-violet-900/40 space-y-2.5 text-xs text-slate-500 dark:text-slate-400">
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5"><Activity size={12} aria-hidden="true" /> Uncertainty band</span>
              <strong className="text-slate-700 dark:text-slate-200 tabular-nums">
                {bandChange >= 0 ? "Widened " : "Narrowed "}{signedPercent(Math.abs(bandChange))}
              </strong>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span>Evidence reviewed</span>
              <strong className="text-slate-700 dark:text-slate-200 tabular-nums">{sampleCount.toLocaleString()} signals</strong>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span>Baseline source</span>
              <strong className="text-slate-700 dark:text-slate-200 capitalize">{titleCase(dataSource)}</strong>
            </div>
          </div>
        </div>

        <div className="p-6 lg:p-7">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">Forecast drivers</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Contribution to the median forecast, in percentage points</p>
            </div>
            <span className="hidden sm:inline-flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400 bg-slate-100/80 dark:bg-slate-800 px-2 py-1 rounded-lg">
              <Info size={11} aria-hidden="true" /> Positive lifts · negative offsets
            </span>
          </div>

          {drivers.length > 0 ? (
            <ol className="space-y-4" aria-label="Forecast driver contributions">
              {drivers.map((driver, index) => {
                const positive = driver.contribution_pct > 0;
                const negative = driver.contribution_pct < 0;
                const DriverIcon = positive ? ArrowUpRight : negative ? ArrowDownRight : Minus;
                const width = Math.max(5, (Math.abs(driver.contribution_pct) / maxImpact) * 100);
                return (
                  <li key={`${driver.source}-${driver.series_key}-${index}`}>
                    <div className="flex items-center gap-3">
                      <span
                        className={clsx(
                          "h-8 w-8 rounded-xl flex items-center justify-center shrink-0",
                          positive && "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/25 dark:text-emerald-300",
                          negative && "bg-rose-50 text-rose-700 dark:bg-rose-900/25 dark:text-rose-300",
                          !positive && !negative && "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300",
                        )}
                      >
                        <DriverIcon size={15} aria-hidden="true" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex items-center gap-2">
                            <span className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">
                              {explanationDriverLabel(driver)}
                            </span>
                            <span className="hidden sm:inline rounded-md bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 shrink-0">
                              {sourceLabel(driver.source)}
                            </span>
                          </div>
                          <strong
                            className={clsx(
                              "text-xs tabular-nums shrink-0",
                              positive && "text-emerald-700 dark:text-emerald-300",
                              negative && "text-rose-700 dark:text-rose-300",
                              !positive && !negative && "text-slate-500",
                            )}
                          >
                            {signedPoints(driver.contribution_pct)}
                          </strong>
                        </div>
                        <div className="mt-1.5 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                          <div
                            className={clsx("h-full rounded-full", positive ? "bg-emerald-500" : negative ? "bg-rose-500" : "bg-slate-400")}
                            style={{ width: `${width}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className="min-h-40 rounded-2xl border border-dashed border-slate-200 dark:border-slate-700 flex flex-col items-center justify-center text-center px-5">
              <Minus size={18} className="text-slate-400" aria-hidden="true" />
              <p className="mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200">No material external adjustment</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Recent signals were neutral, unavailable, or offset one another.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
