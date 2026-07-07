import { useState } from "react";
import { TrendingDown, TrendingUp, Minus, Sparkles, ChevronDown } from "lucide-react";
import clsx from "clsx";
import type { TrendScore } from "@/types/api";
import { groupDrivers } from "@/utils/driverGroups";

interface Props {
  score: TrendScore | null | undefined;
  loading?: boolean;
}

// Plain-English names for each signal type.
const KIND_LABEL: Record<string, string> = {
  economic_indicator: "Economy & weather",
  social_buzz: "Social media buzz",
  search_interest: "Online searches",
  news_sentiment: "Fashion news",
  commodity_price: "Material costs",
};

// Where a signal comes from — shown as a small tag so users know the source.
function sourceTag(seriesKey: string, source: string): string {
  const k = seriesKey.toLowerCase();
  if (k.startsWith("google:")) return "Google";
  if (k.startsWith("reddit:")) return "Reddit";
  if (k.startsWith("pinterest:")) return "Pinterest";
  if (k.startsWith("tiktok:")) return "TikTok";
  if (k.startsWith("instagram:")) return "Instagram";
  if (k.startsWith("weather:")) return "Weather";
  if (k.startsWith("competitor:")) return "Competitors";
  if (k.startsWith("fred:")) return "Economy";
  return source.replace(/_/g, " ");
}

function dirOf(val: number): "up" | "down" | "flat" {
  return val > 0.05 ? "up" : val < -0.05 ? "down" : "flat";
}

// Friendly "what's happening" words instead of jargon like "Strong boost".
function strengthLabel(val: number): string {
  const abs = Math.abs(val);
  if (abs < 0.05) return "Steady";
  if (val > 0) return abs >= 0.5 ? "Strong lift" : abs >= 0.2 ? "Lift" : "Slight lift";
  return abs >= 0.5 ? "Strong drop" : abs >= 0.2 ? "Drop" : "Slight dip";
}

// One plain sentence summarising the overall trend.
function verdict(score: number): string {
  if (score >= 0.2) return "Shoppers want more — demand is heating up.";
  if (score >= 0.05) return "Demand is ticking up a little.";
  if (score > -0.05) return "Demand looks steady.";
  if (score > -0.2) return "Demand is easing off a little.";
  return "Demand is cooling down.";
}

// Friendly names for signals whose raw key reads badly (e.g. subreddits).
const KNOWN_LABELS: Record<string, string> = {
  "reddit:r/femalefashionadvice": "Women's fashion",
  "reddit:r/malefashionadvice": "Men's fashion",
  "reddit:r/streetwear": "Streetwear",
  "reddit:r/sneakers": "Sneakers",
  "pinterest:minimalist_wardrobe": "Minimalist wardrobe",
  "pinterest:streetwear_aesthetic": "Streetwear looks",
  "tiktok:thriftflip": "Thrift flips",
  "tiktok:ootd": "Outfit-of-the-day",
};

function cleanDriverLabel(seriesKey: string): string {
  const known = KNOWN_LABELS[seriesKey.toLowerCase()];
  if (known) return known;
  const label = seriesKey
    .replace(/^(google:|reddit:r\/|reddit:|fred:|weather:|pinterest:|tiktok:|instagram:|competitor:[a-z]+:)/, "")
    .replace(/[:_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
  return label.replace(/\bNyc\b/g, "NYC");
}

export const TrendPanel = ({ score, loading }: Props) => {
  if (loading) {
    return (
      <div className="glass rounded-2xl p-6 animate-pulse">
        <div className="h-5 w-40 bg-white/10 rounded mb-4" />
        <div className="h-12 w-32 bg-white/10 rounded" />
      </div>
    );
  }

  if (!score) {
    return (
      <div className="glass rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-slate-800">Market Trend</h3>
        <div className="text-slate-500 text-sm mt-2">No signals available yet.</div>
      </div>
    );
  }

  const direction =
    score.score > 0.05 ? "up" : score.score < -0.05 ? "down" : "flat";
  const Icon =
    direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;
  const directionColor = {
    up: "text-emerald-400",
    down: "text-rose-400",
    flat: "text-slate-500",
  }[direction];

  // Sources "agree" when they don't disagree — friendlier than raw volatility.
  const agreement = Math.max(0, Math.min(100, (1 - score.volatility) * 100));
  const agreeWord =
    score.volatility < 0.2 ? "They mostly agree"
    : score.volatility < 0.5 ? "Somewhat mixed"
    : "Mixed — treat as rough";

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-200/70">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={14} className="text-violet-300" />
            <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
              Market Trend
            </h3>
          </div>
          <p className="text-xs text-slate-500">
            What shoppers want right now — and why
          </p>
        </div>
        <div className={clsx("flex items-center gap-1", directionColor)}>
          <Icon size={20} />
          <span className="text-3xl font-bold tabular-nums">
            {score.score >= 0 ? "+" : ""}
            {(score.score * 100).toFixed(0)}
          </span>
        </div>
      </div>

      {/* Plain-English verdict */}
      <p className="mt-3 text-sm font-medium text-slate-700 leading-snug">
        {verdict(score.score)}
      </p>
      <p className="mt-1 text-[11px] text-slate-400">
        Based on {score.sample_count.toLocaleString()} signals from the last {score.horizon_days} days.
        Score runs from −100 (very weak) to +100 (very strong).
      </p>

      {/* Do the signals agree? (was "signal volatility") */}
      <div className="mt-5">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500 mb-1">
          <span>Do the signals agree?</span>
          <span className="font-semibold normal-case">{agreeWord}</span>
        </div>
        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-rose-300 via-amber-300 to-emerald-400"
            style={{ width: `${agreement}%` }}
          />
        </div>
      </div>

      {/* Where the trend is coming from (per signal type) */}
      {Object.keys(score.by_kind).length > 0 && (
        <div className="mt-5 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
            Where it's coming from
          </div>
          {Object.entries(score.by_kind).map(([kind, val]) => {
            const dir = dirOf(val);
            const KindIcon = dir === "up" ? TrendingUp : dir === "down" ? TrendingDown : Minus;
            const kindColor = dir === "up" ? "text-emerald-500" : dir === "down" ? "text-rose-500" : "text-slate-400";
            return (
              <div key={kind} className="flex items-center gap-2">
                <KindIcon size={11} className={clsx("shrink-0", kindColor)} />
                <span className="text-xs text-slate-500 w-32 shrink-0">
                  {KIND_LABEL[kind] || kind}
                </span>
                <div className="flex-1 h-1 rounded-full bg-slate-100 overflow-hidden relative">
                  <div
                    className={clsx(
                      "h-full absolute top-0",
                      val >= 0 ? "bg-emerald-400" : "bg-rose-400",
                    )}
                    style={{
                      width: `${Math.min(50, Math.abs(val) * 50)}%`,
                      left: val >= 0 ? "50%" : `${50 - Math.min(50, Math.abs(val) * 50)}%`,
                    }}
                  />
                  <div className="absolute top-0 left-1/2 w-px h-full bg-slate-300" />
                </div>
                <span className={clsx("text-[10px] w-20 text-right font-medium", kindColor)}>
                  {strengthLabel(val)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* What shoppers are into right now */}
      {score.drivers.length > 0 && (
        <DriverList
          title="Trending Products"
          hint="What shoppers are into right now"
          items={score.drivers}
          max={5}
        />
      )}

      {/* Things that can also move demand (weather, economy, competitors) */}
      {(score.demand_factors?.length ?? 0) > 0 && (
        <DriverList
          title="Other things to watch"
          hint="These can also push demand up or down"
          items={score.demand_factors!}
          max={3}
          subtle
        />
      )}
    </div>
  );
};

interface DriverListProps {
  title: string;
  hint: string;
  items: { series_key: string; source: string; score: number; weight?: number }[];
  max: number;
  subtle?: boolean;
}

function DriverList({ title, hint, items, max, subtle }: DriverListProps) {
  const groups = groupDrivers(items, cleanDriverLabel, sourceTag).slice(0, max);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  return (
    <div className="mt-5 pt-4 border-t border-slate-200/70">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {title}
      </div>
      <div className="text-[11px] text-slate-400 mb-2.5">{hint}</div>
      <ul className="space-y-2">
        {groups.map((g, i) => {
          const dir = dirOf(g.consensus);
          const DIcon = dir === "up" ? TrendingUp : dir === "down" ? TrendingDown : Minus;
          const dColor = dir === "up" ? "text-emerald-500" : dir === "down" ? "text-rose-500" : "text-slate-400";
          const dBg = dir === "up" ? "bg-emerald-50" : dir === "down" ? "bg-rose-50" : "bg-slate-50";
          const multi = g.sources.length > 1;
          const isOpen = open[g.label] ?? false;

          return (
            <li key={i}>
              <div
                className={clsx("flex items-start gap-2", multi && "cursor-pointer")}
                onClick={() => multi && setOpen((o) => ({ ...o, [g.label]: !isOpen }))}
              >
                <div className={clsx("mt-0.5 w-5 h-5 rounded-md flex items-center justify-center shrink-0", subtle ? "bg-slate-50" : dBg)}>
                  <DIcon size={11} className={subtle ? "text-slate-400" : dColor} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={clsx("text-xs font-medium leading-tight truncate", subtle ? "text-slate-500" : "text-slate-700")}>
                      {g.label}
                    </span>
                    {multi ? (
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 text-[9px] uppercase tracking-wide rounded px-1 py-px shrink-0",
                          g.conflict ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700",
                        )}
                      >
                        {g.conflict ? "Mixed" : "Agree"} · {g.sources.length}
                      </span>
                    ) : (
                      <span className="text-[9px] uppercase tracking-wide text-slate-400 bg-slate-100 rounded px-1 py-px shrink-0">
                        {g.sources[0]?.tag}
                      </span>
                    )}
                    {multi && (
                      <ChevronDown size={11} className={clsx("text-slate-400 transition-transform shrink-0", isOpen && "rotate-180")} />
                    )}
                  </div>
                  <div className={clsx("text-[10px] font-medium mt-0.5", subtle ? "text-slate-400" : dColor)}>
                    {strengthLabel(g.consensus)}
                    {g.conflict && <span className="text-amber-600"> · sources disagree</span>}
                  </div>
                </div>
              </div>

              {multi && isOpen && (
                <ul className="mt-1.5 ml-7 space-y-1">
                  {g.sources.map((s, si) => {
                    const sDir = dirOf(s.score);
                    const sColor = sDir === "up" ? "text-emerald-500" : sDir === "down" ? "text-rose-500" : "text-slate-400";
                    const SIcon = sDir === "up" ? TrendingUp : sDir === "down" ? TrendingDown : Minus;
                    return (
                      <li key={si} className="flex items-center gap-1.5">
                        <SIcon size={10} className={clsx("shrink-0", sColor)} />
                        <span className="text-[10px] text-slate-500 flex-1 truncate">{s.tag}</span>
                        <span className={clsx("text-[10px] font-medium", sColor)}>{strengthLabel(s.score)}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
