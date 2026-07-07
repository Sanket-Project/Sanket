import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw,
  Activity,
  TrendingUp,
  TrendingDown,
  Minus,
  Sprout,
  Cpu,
  Shirt,
  Pill,
  Wrench,
  Globe,
  MessageSquare,
  BarChart2,
  Zap,
  Info,
  ChevronDown,
  MapPin,
  SlidersHorizontal,
  Truck,
  CloudSun,
} from "lucide-react";
import clsx from "clsx";
import { groupDrivers, type GroupedDriver } from "@/utils/driverGroups";
import { ALL_STATES } from "@/utils/indiaRegions";
import toast from "react-hot-toast";
import { getErrorMessage } from "@/utils/errors";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { trendsApi } from "@/api/trends";
import { useIndustryStore } from "@/stores/industry";
import type { TrendScore, TrendSignal, IndustryCode } from "@/types/api";

// ─────────────────────────────────────────────────────────────────────────────
// Industry config — theme colours, labels, icons, descriptions
// ─────────────────────────────────────────────────────────────────────────────
const INDUSTRY_CONFIG: Record<
  IndustryCode,
  {
    label: string;
    icon: React.ReactNode;
    accent: string;
    accentLight: string;
    accentBorder: string;
    gradient: string;
    description: string;
  }
> = {
  agrocenter: {
    label: "Agrocenter & Farm Inputs",
    icon: <Sprout size={18} />,
    accent: "text-emerald-600 dark:text-emerald-400",
    accentLight: "bg-emerald-50 dark:bg-emerald-900/20",
    accentBorder: "border-emerald-200 dark:border-emerald-800/50",
    gradient: "from-emerald-500 to-teal-600",
    description:
      "Tracks weather events, commodity prices, planting seasonality, and regulatory signals affecting farm-input demand.",
  },
  electronics: {
    label: "Consumer Electronics",
    icon: <Cpu size={18} />,
    accent: "text-cyan-600 dark:text-cyan-400",
    accentLight: "bg-cyan-50 dark:bg-cyan-900/20",
    accentBorder: "border-cyan-200 dark:border-cyan-800/50",
    gradient: "from-cyan-500 to-blue-600",
    description:
      "Monitors component supply signals, product launch cycles, competitor pricing moves, and consumer electronics search trends.",
  },
  fashion: {
    label: "Apparel & Fashion",
    icon: <Shirt size={18} />,
    accent: "text-pink-600 dark:text-pink-400",
    accentLight: "bg-pink-50 dark:bg-pink-900/20",
    accentBorder: "border-pink-200 dark:border-pink-800/50",
    gradient: "from-pink-500 to-fuchsia-600",
    description:
      "Analyses social buzz, fashion influencer sentiment, runway trend signals, and seasonal sell-through patterns.",
  },
  pharma: {
    label: "Pharmaceuticals",
    icon: <Pill size={18} />,
    accent: "text-teal-600 dark:text-teal-400",
    accentLight: "bg-teal-50 dark:bg-teal-900/20",
    accentBorder: "border-teal-200 dark:border-teal-800/50",
    gradient: "from-teal-500 to-cyan-600",
    description:
      "Tracks disease prevalence, regulatory approvals, generic competition, and healthcare spend indicators.",
  },
  hardware: {
    label: "Hardware & Industrial Supply",
    icon: <Wrench size={18} />,
    accent: "text-orange-600 dark:text-orange-400",
    accentLight: "bg-orange-50 dark:bg-orange-900/20",
    accentBorder: "border-orange-200 dark:border-orange-800/50",
    gradient: "from-orange-500 to-amber-600",
    description:
      "Monitors commodity prices (steel, copper), freight & supplier lead times, construction activity, and competitor pricing across hardware categories.",
  },
};const INDUSTRY_PRODUCTS: Record<IndustryCode, { kw: string; label: string }[]> = {
  fashion: [
    { kw: "sneakers", label: "Sneakers (Footwear)" },
    { kw: "printed t-shirts", label: "Printed T-Shirts (Tops)" },
    { kw: "jeans", label: "Jeans (Bottoms)" },
  ],
  electronics: [
    { kw: "gaming laptops", label: "Gaming Laptops (Computing)" },
    { kw: "smartphones", label: "Smartphones (Mobile)" },
    { kw: "smart watches", label: "Smart Watches (Wearables)" },
  ],
  pharma: [
    { kw: "allergy medicine", label: "Allergy Medicine (OTC)" },
    { kw: "vaccines", label: "Vaccines (Clinical)" },
    { kw: "cough syrup", label: "Cough Syrup (Generic)" },
  ],
  agrocenter: [
    { kw: "pesticides", label: "Pesticides (Agri Inputs)" },
    { kw: "urea fertilizer", label: "Urea Fertilizer (Commodities)" },
    { kw: "tractors", label: "Tractors (Machinery)" },
  ],
  hardware: [
    { kw: "cordless drill", label: "Cordless Drill (Power Tools)" },
    { kw: "pvc pipe", label: "PVC Pipe (Plumbing)" },
    { kw: "electrical wire", label: "Electrical Wire (Electrical)" },
  ],
};
// ─────────────────────────────────────────────────────────────────────────────
// Product + regional demand helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Resolve a demand keyword (e.g. "printed t-shirts") to a clean product name
 *  and its category, using the industry product catalog. */
function productMeta(industry: IndustryCode, kw: string): { name: string; category: string } {
  const entry = (INDUSTRY_PRODUCTS[industry] || []).find(
    (p) => p.kw.toLowerCase() === String(kw).toLowerCase(),
  );
  if (entry) {
    const m = entry.label.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
    if (m) return { name: m[1].trim(), category: m[2].trim() };
    return { name: entry.label, category: "" };
  }
  const name = String(kw || "")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
  return { name, category: "" };
}

/** Build the "Top Demand Drivers" rows keyed by PRODUCT (not by news source).
 *  Aggregates the per-city regional demand signals into one consensus row per
 *  product so the panel reads as "Sneakers +42", "Jeans −18", etc. */
function buildProductDrivers(regional: TrendSignal[], industry: IndustryCode): GroupedDriver[] {
  const byProduct = new Map<string, { kw: string; sum: number; wsum: number }>();
  for (const r of regional) {
    const kw = String((r.payload as any)?.product || "").trim();
    if (!kw) continue;
    const key = kw.toLowerCase();
    const w = Math.max(0.1, Number(r.confidence) || 0.5);
    const g = byProduct.get(key) ?? { kw, sum: 0, wsum: 0 };
    g.sum += Number(r.normalized_score) * w;
    g.wsum += w;
    byProduct.set(key, g);
  }

  const out: GroupedDriver[] = [];
  for (const { kw, sum, wsum } of byProduct.values()) {
    const consensus = wsum > 0 ? sum / wsum : 0;
    const { name, category } = productMeta(industry, kw);
    out.push({
      label: name,
      consensus,
      sources: [{ tag: category || "Demand", score: consensus, weight: 1 }],
      agree: false,
      conflict: false,
      impact: Math.abs(consensus),
    });
  }
  out.sort((a, b) => b.impact - a.impact);
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper utilities
// ─────────────────────────────────────────────────────────────────────────────
const SERIES_LABEL: Record<string, string> = {
  CPIAUCSL: "Consumer Price Index",
  CPIMEDSL: "Medical CPI",
  PPIACO: "Producer Price Index",
  UNRATE: "Unemployment Rate",
  UMCSENT: "Consumer Sentiment",
  PCE: "Personal Consumption",
  INDPRO: "Industrial Production",
};

const KIND_LABEL: Record<string, string> = {
  economic_indicator: "Economy",
  social_buzz: "Social Media",
  search_interest: "Search Trends",
  news_sentiment: "News & Media",
  commodity_price: "Commodity Prices",
  weather: "Weather",
  regulatory: "Regulatory",
};

function cleanLabel(key: string, _source?: string): string {
  const lk = key.toLowerCase();

  // 1. Editorial/Publisher RSS URLs
  if (lk.includes("vogue.in") || lk.includes("vogue")) {
    return "Vogue India Insights";
  }
  if (lk.includes("refinery29.com") || lk.includes("refinery29")) {
    return "Refinery29 Trends";
  }
  if (lk.includes("businessoffashion.com") || lk.includes("businessoffashion") || lk.includes("businessoffashio")) {
    return "Business of Fashion Insights";
  }
  if (lk.includes("fashionista.com") || lk.includes("fashionista")) {
    return "Fashionista Buzz";
  }
  if (lk.includes("hypebeast.com") || lk.includes("hypebeast")) {
    return "Hypebeast Buzz";
  }
  if (lk.includes("wwd.com") || lk.includes("wwd")) {
    return "WWD Fashion Insights";
  }
  if (lk.includes("theverge.com") || lk.includes("theverge")) {
    return "The Verge Tech Buzz";
  }
  if (lk.includes("techcrunch.com") || lk.includes("techcrunch")) {
    return "TechCrunch Tech Insights";
  }
  if (lk.includes("arstechnica.com") || lk.includes("arstechnica")) {
    return "Ars Technica Tech Insights";
  }
  if (lk.includes("fiercepharma.com") || lk.includes("fiercepharma")) {
    return "FiercePharma News";
  }
  if (lk.includes("statnews.com") || lk.includes("statnews")) {
    return "STAT News Insights";
  }
  if (lk.includes("pharmatimes.com") || lk.includes("pharmatimes")) {
    return "PharmaTimes Insights";
  }

  // 2. Weather Temperature Deviations
  if (lk.startsWith("weather:") || lk.includes("temp_deviation")) {
    const parts = key.split(":");
    let city = "";
    if (parts.length >= 2) {
      city = parts[1];
    } else {
      city = key.replace(/weather:|_temp_deviation|temp_deviation/gi, "");
    }
    // Clean city name
    city = city
      .replace(/_/g, " ")
      .replace(/\b(temp|deviation)\b/gi, "")
      .trim();
    if (city.toLowerCase() === "nyc") {
      city = "New York";
    } else if (city.toLowerCase() === "delhi ncr") {
      city = "Delhi NCR";
    } else {
      city = city.replace(/\b\w/g, (c) => c.toUpperCase());
    }
    return `${city} Temperature Deviation`;
  }

  // 3. Logistics Corridor lanes
  if (lk.startsWith("logistics:")) {
    const parts = key.split(":");
    let route = "";
    if (parts.length >= 2) {
      route = parts[1];
    } else {
      route = key.replace(/logistics:/gi, "");
    }
    route = route
      .replace(/_apparel|_electronics|_pharma|_agrocenter/gi, "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
      .trim();
    if (route.toLowerCase().includes("mumbai port to bangalore")) {
      route = "Mumbai Port to Bangalore";
    } else if (route.toLowerCase().includes("nyc port to nj warehouse")) {
      route = "NYC Port to NJ Warehouse";
    }
    return `${route} Transit Efficiency`;
  }

  const knownLabels: Record<string, string> = {
    "reddit:r/femalefashionadvice": "Women's Fashion Advice",
    "reddit:r/malefashionadvice": "Men's Fashion Advice",
    "reddit:r/streetwear": "Streetwear Buzz",
    "reddit:r/sneakers": "Sneakers Buzz",
    "reddit:r/gadgets": "Gadgets Buzz",
    "tiktok:ootd": "Outfit-of-the-Day (TikTok)",
    "pinterest:quiet_luxury_aesthetic": "Quiet Luxury Aesthetic",
    "pinterest:minimalist_wardrobe": "Minimalist Wardrobe",
    "instagram:y2k_fashion": "Y2K Fashion Revival",
    "weather:la_nina_cooling": "La Niña Cooling Front",
    "weather:rainfall_index_west": "Rainfall Index (West)",
    "commodity:urea_fertilizer": "Urea Fertilizer Price",
    "commodity:lithium_price": "Lithium Battery Cost",
    "competitor:syngenta_price_cut": "Competitor Price Cut",
    "competitor:samsung_price_drop": "Samsung Price Drop",
    "news:chip shortage 2026": "Chip Shortage Report",
    "news:fda_approval_oncology": "FDA Oncology Approval",
    "news:generic_competition_metformin": "Generic Metformin Competition",
    "news:insurance_coverage_change": "Insurance Coverage Change",
    "news:crop yield forecast": "Crop Yield Forecast",
  };
  if (knownLabels[lk]) return knownLabels[lk];
  return key
    .replace(/^(google:|reddit:r\/|reddit:|fred:|news:|weather:|pinterest:|tiktok:|instagram:|competitor:[a-z]+:)/i, "")
    .replace(/[_:-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function sourceTag(key: string, source: string): string {
  const k = key.toLowerCase();
  if (k.startsWith("google:")) return "Google";
  if (k.startsWith("reddit:")) return "Reddit";
  if (k.startsWith("pinterest:")) return "Pinterest";
  if (k.startsWith("tiktok:")) return "TikTok";
  if (k.startsWith("instagram:")) return "Instagram";
  if (k.startsWith("weather:")) return "Weather";
  if (k.startsWith("competitor:")) return "Competitor";
  if (k.startsWith("commodity:")) return "Commodity";
  if (k.startsWith("news:")) return "News";
  if (source === "fred") return "FRED";
  if (source === "google_trends") return "Google";
  if (source === "news_api") return "News";
  return source.replace(/_/g, " ");
}

function dirOf(val: number) {
  return val > 0.05 ? "up" : val < -0.05 ? "down" : "flat";
}

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

function strengthLabel(val: number) {
  const abs = Math.abs(val);
  if (abs < 0.05) return "Neutral";
  if (val > 0) return abs >= 0.5 ? "Strong lift" : abs >= 0.2 ? "Lift" : "Slight lift";
  return abs >= 0.5 ? "Strong drag" : abs >= 0.2 ? "Drag" : "Slight drag";
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** Big trend score gauge card */
function TrendScoreGauge({ score, loading, industry }: { score: TrendScore | undefined; loading: boolean; industry: IndustryCode }) {
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
  const pct = scoreToPercent(data.score);
  const v = verdict(data.score);
  const agreement = Math.round((1 - data.volatility) * 100);

  const STROKE = 10;
  const R = 54;
  const CIRC = 2 * Math.PI * R;
  const dash = (pct / 100) * CIRC;

  const dirColor =
    v.tone === "up" ? "#10b981" : v.tone === "down" ? "#ef4444" : "#94a3b8";
  const DirIcon = v.tone === "up" ? TrendingUp : v.tone === "down" ? TrendingDown : Minus;

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-100/80 dark:shadow-none relative overflow-hidden">
      <div className={clsx("absolute top-0 left-0 right-0 h-1 bg-gradient-to-r", cfg.gradient)} />

      <div className="flex items-center gap-2 mb-5">
        <span className={cfg.accent}>{cfg.icon}</span>
        <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
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
            <circle cx={64} cy={64} r={R} fill="none" stroke="#e2e8f0" strokeWidth={STROKE} className="dark:stroke-slate-700" />
            {/* Fill */}
            <circle
              cx={64} cy={64} r={R}
              fill="none"
              stroke={dirColor}
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${dash} ${CIRC}`}
              strokeDashoffset={CIRC * 0.25}
              style={{ transition: "stroke-dasharray 1s cubic-bezier(0.34,1.56,0.64,1)", filter: `drop-shadow(0 0 6px ${dirColor}40)` }}
            />
          </svg>
          {/* Center value */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <DirIcon size={16} style={{ color: dirColor }} />
            <span className="text-2xl font-black tabular-nums" style={{ color: dirColor }}>
              {data.score >= 0 ? "+" : ""}{Math.round(data.score * 100)}
            </span>
            <span className="text-[9px] text-slate-400 dark:text-slate-500 font-semibold uppercase tracking-wider">score</span>
          </div>
        </div>

        <div className="flex-1 min-w-0 space-y-3">
          <div>
            <p className="text-base font-bold text-slate-800 dark:text-slate-100 leading-snug">{v.text}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{v.sub}</p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span className="text-slate-500 dark:text-slate-400">
                <strong className="text-slate-700 dark:text-slate-200">{data.sample_count.toLocaleString()}</strong> signals
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-violet-400" />
              <span className="text-slate-500 dark:text-slate-400">{data.horizon_days}d horizon</span>
            </div>
          </div>
        </div>
      </div>

      {/* Agreement bar */}
      <div className="mt-5">
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-1.5">
          <span>Signal agreement</span>
          <span className={agreement >= 70 ? "text-emerald-600 dark:text-emerald-400" : agreement >= 50 ? "text-amber-600 dark:text-amber-400" : "text-rose-500 dark:text-rose-400"}>
            {agreement >= 70 ? "High" : agreement >= 50 ? "Moderate" : "Low"} ({agreement}%)
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-700/60 overflow-hidden">
          <div
            className="h-2 rounded-full bg-gradient-to-r from-rose-300 via-amber-300 to-emerald-400 transition-all duration-700"
            style={{ width: `${agreement}%` }}
          />
        </div>
        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
          {agreement >= 70 ? "Sources are largely aligned — high confidence" : agreement >= 50 ? "Mixed signals — treat forecasts as directional" : "Sources conflict — treat as rough estimate"}
        </p>
      </div>
    </div>
  );
}

/** By-kind breakdown bars */
function SignalBreakdown({ score, industry }: { score: TrendScore | undefined; industry: IndustryCode }) {
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
  const entries = Object.entries(data.by_kind);

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-100/80 dark:shadow-none">
      <div className="flex items-center gap-2 mb-5">
        <BarChart2 size={15} className="text-violet-500 dark:text-violet-400" />
        <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
          Signal Breakdown
        </h3>
        <span className="ml-auto text-[10px] text-slate-400 dark:text-slate-500 font-medium">
          by source type
        </span>
      </div>

      <div className="space-y-3">
        {entries.map(([kind, val]) => {
          const dir = dirOf(val);
          const DirIcon = dir === "up" ? TrendingUp : dir === "down" ? TrendingDown : Minus;
          const color = dir === "up" ? "#10b981" : dir === "down" ? "#ef4444" : "#94a3b8";
          const barPct = Math.min(100, Math.abs(val) * 100);

          return (
            <div key={kind}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <DirIcon size={11} style={{ color }} />
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                    {KIND_LABEL[kind] ?? kind}
                  </span>
                </div>
                <span className="text-[10px] font-bold" style={{ color }}>
                  {strengthLabel(val)}
                </span>
              </div>
              {/* Diverging bar centred at 50% */}
              <div className="relative h-1.5 rounded-full bg-slate-100 dark:bg-slate-700/60 overflow-hidden">
                <div className="absolute top-0 left-1/2 w-px h-full bg-slate-300 dark:bg-slate-600" />
                <div
                  className="absolute top-0 h-full rounded-full transition-all duration-700"
                  style={{
                    background: color,
                    width: `${barPct / 2}%`,
                    left: val >= 0 ? "50%" : `${50 - barPct / 2}%`,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Top demand drivers — ranked by product. Aggregates the regional demand
 *  signals into one consensus row per product so the panel headlines the actual
 *  products (Sneakers, Jeans…) rather than the news source that mentioned them.
 *  Falls back to the raw fused drivers when no product-level data is available. */
function TopDrivers({
  score,
  industry,
  regional,
}: {
  score: TrendScore | undefined;
  industry: IndustryCode;
  regional: TrendSignal[];
}) {
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
  const productGroups = buildProductDrivers(regional, industry);
  const groups =
    productGroups.length > 0
      ? productGroups.slice(0, 6)
      : groupDrivers(
          [...(data.drivers ?? []), ...(data.demand_factors ?? [])],
          cleanLabel,
          sourceTag,
        ).slice(0, 6);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-100/80 dark:shadow-none">
      <div className="flex items-center gap-2 mb-5">
        <Zap size={15} className="text-amber-500 dark:text-amber-400" />
        <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
          Top Demand Drivers
        </h3>
        <span className="ml-auto text-[10px] text-slate-400 dark:text-slate-500 font-medium">
          ranked by impact
        </span>
      </div>

      <div className="space-y-2">
        {groups.map((g, i) => {
          const dir = dirOf(g.consensus);
          const DirIcon = dir === "up" ? TrendingUp : dir === "down" ? TrendingDown : Minus;
          const color = dir === "up" ? "#10b981" : dir === "down" ? "#ef4444" : "#94a3b8";
          const bgClass = dir === "up"
            ? "bg-emerald-50 dark:bg-emerald-900/20"
            : dir === "down"
            ? "bg-rose-50 dark:bg-rose-900/20"
            : "bg-slate-50 dark:bg-slate-800/40";
          const borderClass = dir === "up"
            ? "border-emerald-100 dark:border-emerald-800/40"
            : dir === "down"
            ? "border-rose-100 dark:border-rose-800/40"
            : "border-slate-100 dark:border-slate-700/40";
          const pct = Math.round(Math.abs(g.consensus) * 100);
          const multi = g.sources.length > 1;
          const isOpen = expanded[g.label] ?? false;

          return (
            <div
              key={i}
              className={clsx("rounded-xl border transition-all hover:shadow-sm", bgClass, borderClass)}
            >
              <button
                type="button"
                disabled={!multi}
                onClick={() => multi && setExpanded((e) => ({ ...e, [g.label]: !isOpen }))}
                className={clsx("w-full flex items-center gap-3 p-2.5 text-left", multi && "cursor-pointer")}
              >
                <div className="shrink-0 w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: `${color}18` }}>
                  <DirIcon size={12} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">{g.label}</span>
                    {multi ? (
                      <span
                        className={clsx(
                          "shrink-0 inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded",
                          g.conflict
                            ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                            : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
                        )}
                      >
                        <span className={clsx("h-1.5 w-1.5 rounded-full", g.conflict ? "bg-amber-500" : "bg-emerald-500")} />
                        {g.conflict ? "Mixed" : "Agree"} · {g.sources.length}
                      </span>
                    ) : (
                      <span className="shrink-0 text-[9px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-700/60 px-1.5 py-0.5 rounded">
                        {g.sources[0]?.tag}
                      </span>
                    )}
                  </div>
                  <div className="h-1 mt-1.5 rounded-full bg-slate-200 dark:bg-slate-700/60 overflow-hidden">
                    <div className="h-1 rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
                  </div>
                </div>
                <span className="shrink-0 text-[10px] font-bold tabular-nums" style={{ color }}>
                  {g.consensus >= 0 ? "+" : ""}{pct}
                </span>
                {multi && (
                  <ChevronDown
                    size={13}
                    className={clsx("shrink-0 text-slate-400 transition-transform", isOpen && "rotate-180")}
                  />
                )}
              </button>

              {multi && isOpen && (
                <div className="px-2.5 pb-2.5 pt-0.5 space-y-1.5 border-t border-slate-200/60 dark:border-slate-700/40 mt-0.5">
                  {g.sources.map((s, si) => {
                    const sDir = dirOf(s.score);
                    const sColor = sDir === "up" ? "#10b981" : sDir === "down" ? "#ef4444" : "#94a3b8";
                    const SIcon = sDir === "up" ? TrendingUp : sDir === "down" ? TrendingDown : Minus;
                    const sPct = Math.round(Math.abs(s.score) * 100);
                    return (
                      <div key={si} className="flex items-center gap-2 pl-1">
                        <SIcon size={10} style={{ color: sColor }} className="shrink-0" />
                        <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400 flex-1 truncate">{s.tag}</span>
                        <span className="text-[10px] font-bold tabular-nums" style={{ color: sColor }}>
                          {s.score >= 0 ? "+" : ""}{sPct}
                        </span>
                      </div>
                    );
                  })}
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 pt-0.5 leading-snug">
                    {g.conflict
                      ? "Sources disagree — the score above is their net; treat as uncertain."
                      : "Sources agree — combined into the score above."}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Economic indicators table */
function EconomicPanel({ signals, loading }: { signals: TrendSignal[]; loading: boolean }) {
  const rows = signals;
  const deduped = new Map<string, TrendSignal>();
  rows.forEach((s) => {
    const ex = deduped.get(s.series_key);
    if (!ex || new Date(s.captured_at) > new Date(ex.captured_at)) deduped.set(s.series_key, s);
  });
  const sorted = Array.from(deduped.values()).sort((a, b) => Math.abs(b.normalized_score) - Math.abs(a.normalized_score));

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-100/80 dark:shadow-none">
      <div className="flex items-center gap-2 mb-5">
        <Globe size={15} className="text-cyan-500 dark:text-cyan-400" />
        <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
          Economic Indicators
        </h3>
        <span className="ml-auto text-[10px] bg-cyan-50 dark:bg-cyan-900/30 text-cyan-600 dark:text-cyan-400 border border-cyan-200 dark:border-cyan-800/40 px-2 py-0.5 rounded-full font-semibold">
          FRED Data
        </span>
      </div>

      {loading && rows.length === 0 ? (
        <div className="space-y-2 animate-pulse">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-12 rounded-xl bg-slate-100 dark:bg-slate-800/40" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((s) => {
            const score = Number(s.normalized_score);
            const dir = dirOf(score);
            const DirIcon = dir === "up" ? TrendingUp : dir === "down" ? TrendingDown : Minus;
            const color = dir === "up" ? "#10b981" : dir === "down" ? "#ef4444" : "#94a3b8";
            const bgClass = dir === "up" ? "bg-emerald-50 dark:bg-emerald-900/15" : dir === "down" ? "bg-rose-50 dark:bg-rose-900/15" : "bg-slate-50 dark:bg-slate-800/30";
            const borderClass = dir === "up" ? "border-emerald-100 dark:border-emerald-800/30" : dir === "down" ? "border-rose-100 dark:border-rose-800/30" : "border-slate-100 dark:border-slate-700/30";
            const conf = Math.round((s.confidence ?? 0.8) * 100);

            return (
              <div key={s.id} className={clsx("flex items-center gap-3 p-3 rounded-xl border", bgClass, borderClass)}>
                <div className="shrink-0 h-8 w-8 rounded-lg flex items-center justify-center" style={{ background: `${color}15` }}>
                  <DirIcon size={14} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">
                      {SERIES_LABEL[s.series_key] ?? s.series_key}
                    </span>
                    {s.raw_value !== null && (
                      <span className="text-[10px] tabular-nums text-slate-500 dark:text-slate-400 shrink-0">
                        {Number(s.raw_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 h-1 rounded-full bg-slate-200 dark:bg-slate-700/60 overflow-hidden">
                      <div className="h-1 rounded-full" style={{ width: `${conf}%`, background: color }} />
                    </div>
                    <span className="text-[9px] font-semibold text-slate-400 dark:text-slate-500 shrink-0">{conf}% conf.</span>
                    <span className="text-[10px] font-bold shrink-0" style={{ color }}>{strengthLabel(score)}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Social & search signals */
function SocialPanel({ signals, loading }: { signals: TrendSignal[]; loading: boolean }) {
  const rows = signals;
  const deduped = new Map<string, TrendSignal>();
  rows.forEach((s) => {
    const ex = deduped.get(s.series_key);
    if (!ex || new Date(s.captured_at) > new Date(ex.captured_at)) deduped.set(s.series_key, s);
  });
  const sorted = Array.from(deduped.values()).sort((a, b) => Number(b.normalized_score) - Number(a.normalized_score));

  const SOURCE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
    Google: { bg: "bg-blue-50 dark:bg-blue-900/20", text: "text-blue-700 dark:text-blue-400", border: "border-blue-200 dark:border-blue-800/40" },
    Reddit: { bg: "bg-orange-50 dark:bg-orange-900/20", text: "text-orange-700 dark:text-orange-400", border: "border-orange-200 dark:border-orange-800/40" },
    TikTok: { bg: "bg-slate-900/5 dark:bg-slate-100/5", text: "text-slate-700 dark:text-slate-300", border: "border-slate-200 dark:border-slate-700/40" },
    Pinterest: { bg: "bg-red-50 dark:bg-red-900/20", text: "text-red-700 dark:text-red-400", border: "border-red-200 dark:border-red-800/40" },
    Instagram: { bg: "bg-purple-50 dark:bg-purple-900/20", text: "text-purple-700 dark:text-purple-400", border: "border-purple-200 dark:border-purple-800/40" },
    News: { bg: "bg-amber-50 dark:bg-amber-900/20", text: "text-amber-700 dark:text-amber-400", border: "border-amber-200 dark:border-amber-800/40" },
    Competitor: { bg: "bg-rose-50 dark:bg-rose-900/20", text: "text-rose-700 dark:text-rose-400", border: "border-rose-200 dark:border-rose-800/40" },
    Commodity: { bg: "bg-yellow-50 dark:bg-yellow-900/20", text: "text-yellow-700 dark:text-yellow-400", border: "border-yellow-200 dark:border-yellow-800/40" },
    Weather: { bg: "bg-sky-50 dark:bg-sky-900/20", text: "text-sky-700 dark:text-sky-400", border: "border-sky-200 dark:border-sky-800/40" },
  };

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-100/80 dark:shadow-none">
      <div className="flex items-center gap-2 mb-5">
        <MessageSquare size={15} className="text-violet-500 dark:text-violet-400" />
        <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
          Social, Search & News
        </h3>
        <span className="ml-auto text-[10px] text-slate-400 dark:text-slate-500 font-medium">
          real-time signals
        </span>
      </div>

      {loading && rows.length === 0 ? (
        <div className="space-y-2 animate-pulse">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-12 rounded-xl bg-slate-100 dark:bg-slate-800/40" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((s) => {
            const score = Number(s.normalized_score);
            const dir = dirOf(score);
            const DirIcon = dir === "up" ? TrendingUp : dir === "down" ? TrendingDown : Minus;
            const color = dir === "up" ? "#10b981" : dir === "down" ? "#ef4444" : "#94a3b8";
            const label = cleanLabel(s.series_key);
            const src = sourceTag(s.series_key, s.source);
            const srcStyle = SOURCE_COLORS[src] ?? { bg: "bg-slate-50 dark:bg-slate-800/30", text: "text-slate-600 dark:text-slate-400", border: "border-slate-200 dark:border-slate-700/30" };
            const pct = Math.round(Math.abs(score) * 100);
            const conf = Math.round((s.confidence ?? 0.75) * 100);

            return (
              <div key={s.id} className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 dark:border-slate-700/40 hover:bg-slate-50/50 dark:hover:bg-slate-800/20 transition-colors">
                <div className="shrink-0 h-8 w-8 rounded-lg flex items-center justify-center" style={{ background: `${color}15` }}>
                  <DirIcon size={14} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">{label}</span>
                    <span className={clsx("shrink-0 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border", srcStyle.bg, srcStyle.text, srcStyle.border)}>
                      {src}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1 rounded-full bg-slate-200 dark:bg-slate-700/60 overflow-hidden">
                      <div className="h-1 rounded-full transition-all duration-700" style={{ width: `${conf}%`, background: color }} />
                    </div>
                    <span className="text-[9px] font-semibold text-slate-400 dark:text-slate-500 shrink-0">{conf}% conf.</span>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <span className="text-[10px] font-bold block" style={{ color }}>
                    {score >= 0 ? "+" : ""}{pct}
                  </span>
                  <span className="text-[9px] text-slate-400 dark:text-slate-500">{strengthLabel(score)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Supply chain & environmental signals (logistics corridors & localized weather factors) */
function SupplyChainPanel({ signals, loading }: { signals: TrendSignal[]; loading: boolean }) {
  const rows = signals;
  const deduped = new Map<string, TrendSignal>();
  rows.forEach((s) => {
    const ex = deduped.get(s.series_key);
    if (!ex || new Date(s.captured_at) > new Date(ex.captured_at)) deduped.set(s.series_key, s);
  });
  const sorted = Array.from(deduped.values()).sort((a, b) => Math.abs(b.normalized_score) - Math.abs(a.normalized_score));

  return (
    <div className="glass rounded-2xl p-6 shadow-lg shadow-slate-100/80 dark:shadow-none">
      <div className="flex items-center gap-2 mb-5">
        <Truck size={15} className="text-pink-500 dark:text-pink-400" />
        <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">
          Supply Chain & Weather
        </h3>
        <span className="ml-auto text-[10px] bg-pink-50 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400 border border-pink-200 dark:border-pink-800/40 px-2 py-0.5 rounded-full font-semibold">
          Logistics & Climate
        </span>
      </div>

      {loading && rows.length === 0 ? (
        <div className="space-y-2 animate-pulse">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-12 rounded-xl bg-slate-100 dark:bg-slate-800/40" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((s) => {
            const score = Number(s.normalized_score);
            const dir = dirOf(score);
            const color = dir === "up" ? "#10b981" : dir === "down" ? "#ef4444" : "#94a3b8";
            const bgClass = dir === "up" ? "bg-emerald-50 dark:bg-emerald-900/15" : dir === "down" ? "bg-rose-50 dark:bg-rose-900/15" : "bg-slate-50 dark:bg-slate-800/30";
            const borderClass = dir === "up" ? "border-emerald-100 dark:border-emerald-800/30" : dir === "down" ? "border-rose-100 dark:border-rose-800/30" : "border-slate-100 dark:border-slate-700/30";
            const conf = Math.round((s.confidence ?? 0.8) * 100);

            // Determine if logistics or weather icon should be displayed
            const isLogistics = s.series_key.toLowerCase().startsWith("logistics:");
            const SignalIcon = isLogistics ? Truck : CloudSun;

            return (
              <div key={s.id} className={clsx("flex items-center gap-3 p-3 rounded-xl border", bgClass, borderClass)}>
                <div className="shrink-0 h-8 w-8 rounded-lg flex items-center justify-center" style={{ background: `${color}15` }}>
                  <SignalIcon size={14} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">
                      {cleanLabel(s.series_key)}
                    </span>
                    {s.raw_value !== null && (
                      <span className="text-[10px] tabular-nums text-slate-500 dark:text-slate-400 shrink-0">
                        {Number(s.raw_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        {isLogistics ? "" : "°C"}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 h-1 rounded-full bg-slate-200 dark:bg-slate-700/60 overflow-hidden">
                      <div className="h-1 rounded-full" style={{ width: `${conf}%`, background: color }} />
                    </div>
                    <span className="text-[9px] font-semibold text-slate-400 dark:text-slate-500 shrink-0">{conf}% conf.</span>
                    <span className="text-[10px] font-bold shrink-0" style={{ color }}>{strengthLabel(score)}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** "How this works" explainer — contextual to industry */
function HowItWorksCard({ industry }: { industry: IndustryCode }) {
  const STEPS: Record<IndustryCode, { color: string; title: string; desc: string }[]> = {
    agrocenter: [
      { color: "emerald", title: "Weather & Seasonal Overlay", desc: "La Niña / El Niño patterns, rainfall indices, and early-frost alerts are mapped to input categories to predict demand spikes weeks in advance." },
      { color: "teal", title: "Commodity Price Tracking", desc: "Live FRED commodity feeds (urea, potash, diesel) are normalised and weighted to adjust baseline demand quantiles up or down." },
      { color: "amber", title: "Planting-Cycle Integration", desc: "A proprietary planting-season calendar auto-widens the P10–P90 forecast band during peak uncertainty windows (pre-planting ± 2 weeks)." },
    ],
    electronics: [
      { color: "cyan", title: "Component Supply Sensing", desc: "Supplier lead-time feeds and commodity prices (lithium, TSMC wafer indices) are merged to detect supply-side constraints before they impact shelves." },
      { color: "blue", title: "Search & Launch Signals", desc: "Google Trends spikes for product categories are cross-referenced with known launch calendars to separate genuine demand from hype." },
      { color: "rose", title: "Competitor Price Response", desc: "Detected price changes from major competitors automatically widen uncertainty bands and flag potential market-share shifts." },
    ],
    fashion: [
      { color: "pink", title: "Social Trend Velocity", desc: "TikTok, Pinterest, and Instagram trend momentum scores are combined into a single velocity index that leads sell-through by 2–4 weeks." },
      { color: "fuchsia", title: "Runway & Press Signals", desc: "Fashion-week coverage sentiment and editorial mentions are processed via NLP to detect emerging styles before they hit mainstream search." },
      { color: "violet", title: "Sell-Through Seasonality", desc: "Category-level sell-through history is overlaid with trend scores to automatically calibrate the forecast band for seasonal volatility." },
    ],
    pharma: [
      { color: "teal", title: "Disease Prevalence Tracking", desc: "Flu-season forecasts, allergy indices, and CDC prevalence reports are integrated to shift demand projections for relevant drug categories." },
      { color: "cyan", title: "Regulatory Event Detection", desc: "FDA approval announcements and patent-cliff events are automatically flagged and mapped to affected SKUs for proactive stock adjustment." },
      { color: "emerald", title: "Generic Competition Signals", desc: "Generic entry detection (patent expirations + first-to-file ANDA filings) triggers automatic downside scenario modelling for branded SKUs." },
    ],
    hardware: [
      { color: "orange", title: "Commodity Price Tracking", desc: "Live steel, copper, and PVC resin indices are normalised and weighted to adjust baseline cost and demand quantiles for affected hardware categories." },
      { color: "amber", title: "Lead-Time & Freight Sensing", desc: "Supplier lead-time feeds and container freight rates are merged to detect supply-side constraints before they impact shelf availability." },
      { color: "yellow", title: "Construction-Cycle Integration", desc: "Housing-starts and construction-spend indicators are overlaid on the forecast band to anticipate project-season demand swings." },
    ],
  };

  const steps = STEPS[industry];

  return (
    <Card
      title={
        <span className="flex items-center gap-2 text-slate-800 dark:text-slate-100">
          <Activity size={15} className="text-violet-500 dark:text-violet-400" />
          How Trend Signals Shape Your Forecasts
        </span>
      }
      description="These signals automatically adjust your baseline demand projections in real time."
    >
      <div className="space-y-4 mt-1">
        {steps.map(({ color, title, desc }, i) => (
          <div key={i} className="flex items-start gap-4 group">
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center font-black text-sm shrink-0 transition-transform duration-200 group-hover:scale-110`}
            style={{
              background: `var(--tw-${color}-50, rgba(99,102,241,0.08))`,
              border: `1px solid var(--tw-${color}-200, rgba(99,102,241,0.2))`,
            }}
          >
            <span className={`text-${color}-600 dark:text-${color}-400 font-black`}>{i + 1}</span>
          </div>
          <div>
            <div className="text-sm font-bold text-slate-800 dark:text-slate-100">{title}</div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed mt-0.5">{desc}</p>
          </div>
        </div>
      ))}
    </div>
    <div className="mt-4 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/70 dark:border-slate-700/40 flex items-start gap-2">
      <Info size={13} className="text-slate-400 dark:text-slate-500 shrink-0 mt-0.5" />
      <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
        Signals run −100 to +100. Positive = demand lift, Negative = demand drag. High volatility = wider P10–P90 forecast band.
      </p>
    </div>
  </Card>
);
}

export const TrendAnalysisPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const qc = useQueryClient();
  const cfg = INDUSTRY_CONFIG[industry];

  // Tab & filtering states
  const [activeTab, setActiveTab] = useState<"overview" | "regional">("overview");
  const [selectedTier, setSelectedTier] = useState<string>("all");
  const [selectedState, setSelectedState] = useState<string>("all");
  const [selectedProduct, setSelectedProduct] = useState<string>("all");

  const score = useQuery({
    queryKey: ["trends", "score", industry],
    queryFn: () => trendsApi.score({ horizon_days: 90, lookback_hours: 168 }),
    refetchInterval: 60_000,
    retry: 1,
  });
  const economic = useQuery({
    queryKey: ["trends", "economic", industry],
    queryFn: () => trendsApi.economic(40),
    refetchInterval: 120_000,
    retry: 1,
  });
  const social = useQuery({
    queryKey: ["trends", "social", industry],
    queryFn: () => trendsApi.social(40),
    refetchInterval: 120_000,
    retry: 1,
  });
  const regional = useQuery({
    queryKey: ["trends", "regional", industry],
    queryFn: () => trendsApi.regional(),
    refetchInterval: 120_000,
    retry: 1,
  });
  const supplyChain = useQuery({
    queryKey: ["trends", "supplyChain", industry],
    queryFn: () => trendsApi.supplyChain(),
    refetchInterval: 120_000,
    retry: 1,
  });

  const refresh = useMutation({
    mutationFn: () => trendsApi.refresh(),
    onSuccess: (data) => {
      const total = Object.values(data.counts ?? {}).reduce((a, b) => a + b, 0);
      toast.success(`Refreshed ${total} signals across all industries`);
      qc.invalidateQueries({ queryKey: ["trends"] });
    },
    onError: (e: unknown) => {
      toast.error(getErrorMessage(e, "Refresh failed"));
    },
  });

  const isBackendDown = score.isError && economic.isError && social.isError && regional.isError && supplyChain.isError;
  const isLoading = score.isPending || economic.isPending || social.isPending || regional.isPending || supplyChain.isPending;
  const lastUpdated = score.dataUpdatedAt
    ? new Date(score.dataUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  const scoreData = score.data;
  const economicData = economic.data ?? [];
  const socialData = social.data ?? [];
  const regionalData = regional.data ?? [];
  const supplyChainData = supplyChain.data ?? [];

  // State deep-dive modal

  // Every state we can drill into (full district lists), unioned with whatever
  // states the live signal feed happens to mention.
  const uniqueStates = Array.from(
    new Set([
      ...ALL_STATES,
      ...regionalData
        .map((item: any) => item.payload?.state)
        .filter((s: any) => s && s !== "Unknown"),
    ])
  ).sort() as string[];

  // When a state is selected we expand to its full district breakdown (modeled
  // per district); otherwise we show the national headline centers from the feed.
  const stateSelected = selectedState !== "all";
  const baseRegional: any[] = stateSelected
    ? regionalData.filter((item: any) => item.payload?.state === selectedState)
    : regionalData;

  // Filter regional demand records based on active user filters
  const filteredRegional = baseRegional.filter((item: any) => {
    const payload = item.payload || {};
    const matchesTier = selectedTier === "all" || String(payload.tier).toLowerCase() === selectedTier.toLowerCase();

    // Normalize keywords comparison to support clean matching
    const itemProd = String(payload.product || "").toLowerCase().replace(/_/g, " ");
    const filterProd = selectedProduct.toLowerCase().replace(/_/g, " ");
    const matchesProduct = selectedProduct === "all" || itemProd === filterProd;

    return matchesTier && matchesProduct;
  });

  // Derived regional analytics
  const sortedByScore = [...filteredRegional].sort((a, b) => Number(b.normalized_score) - Number(a.normalized_score));
  const topGrowthRegion = sortedByScore[0];
  const coolestRegion = sortedByScore[sortedByScore.length - 1];

  const getTierAvg = (tierName: string) => {
    const sList = baseRegional.filter((s: any) => String(s.payload?.tier).toLowerCase() === tierName.toLowerCase());
    if (sList.length === 0) return 0;
    const sum = sList.reduce((acc: number, cur: any) => acc + Number(cur.normalized_score), 0);
    return Math.round((sum / sList.length) * 100);
  };
  const t1Avg = getTierAvg("tier1");
  const t2Avg = getTierAvg("tier2");
  const t3Avg = getTierAvg("tier3");

  const activeProducts = INDUSTRY_PRODUCTS[industry] || [];

  return (
    <div className="space-y-6" data-industry={industry}>
      {/* ── Page header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 animate-fade-in stagger-1">
        <div>
          {/* Industry label */}
          <div className={clsx("inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest border mb-3", cfg.accentLight, cfg.accent, cfg.accentBorder)}>
            {cfg.icon}
            {cfg.label}
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Market Trends
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1.5 max-w-2xl leading-relaxed">
            {cfg.description}{" "}
            <span className="text-slate-400 dark:text-slate-500 font-medium">Auto-syncs every 15 minutes.</span>
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3 shrink-0">
          {/* Live status pill */}
          <div className={clsx(
            "flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold",
            isBackendDown
              ? "bg-rose-50 border-rose-200 text-rose-600 dark:bg-rose-950/30 dark:border-rose-900/10 dark:text-rose-450"
              : isLoading
              ? "bg-amber-50 border-amber-200 text-amber-600 dark:bg-amber-955/30 dark:border-amber-900/10 dark:text-amber-450"
              : "bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-955/30 dark:border-emerald-900/10 dark:text-emerald-450"
          )}>
            <span className={clsx("h-1.5 w-1.5 rounded-full", isBackendDown ? "bg-rose-500" : isLoading ? "bg-amber-500 animate-pulse" : "bg-emerald-500 animate-pulse")} />
            {isBackendDown ? "Offline" : isLoading ? "Syncing…" : `Live · ${lastUpdated ?? "—"}`}
          </div>

          <Button
            icon={<RefreshCw size={13} className={refresh.isPending ? "animate-spin" : ""} />}
            onClick={() => refresh.mutate()}
            loading={refresh.isPending}
            variant="secondary"
            size="sm"
            className="tactile-press border border-slate-200 dark:border-slate-700 shadow-sm rounded-xl px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* ── Navigation Tabs ── */}
      <div className="flex border-b border-slate-200 dark:border-slate-800 gap-2 mb-4 animate-fade-in stagger-2">
        <button
          onClick={() => setActiveTab("overview")}
          className={clsx(
            "py-2.5 px-4 text-sm font-bold border-b-2 transition duration-200 focus:outline-none",
            activeTab === "overview"
              ? "border-violet-500 text-violet-600 dark:text-violet-450"
              : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-400"
          )}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab("regional")}
          className={clsx(
            "py-2.5 px-4 text-sm font-bold border-b-2 transition duration-200 flex items-center gap-2 focus:outline-none",
            activeTab === "regional"
              ? "border-violet-500 text-violet-600 dark:text-violet-450"
              : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-400"
          )}
        >
          <MapPin size={14} />
          Regional Insights
        </button>
      </div>

      {activeTab === "overview" ? (
        <>
          {/* ── Row 1: Score gauge + Signal breakdown + Drivers ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 animate-fade-in stagger-3">
            <TrendScoreGauge score={scoreData} loading={isLoading} industry={industry} />
            <SignalBreakdown score={scoreData} industry={industry} />
            <TopDrivers score={scoreData} industry={industry} regional={regionalData} />
          </div>

          {/* ── Row 2: Economic + Supply Chain + Social panels ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 animate-fade-in stagger-4">
            <EconomicPanel signals={economicData} loading={economic.isPending} />
            <SupplyChainPanel signals={supplyChainData} loading={supplyChain.isPending} />
            <SocialPanel signals={socialData} loading={social.isPending} />
          </div>

          {/* ── Row 3: How it works (industry-specific) ── */}
          <div className="animate-fade-in stagger-5">
            <HowItWorksCard industry={industry} />
          </div>
        </>
      ) : (
        <div className="space-y-6 animate-fade-in">
          {/* ── Filters Section ── */}
          <div className="glass rounded-2xl p-5 shadow-lg shadow-slate-100/80 dark:shadow-none border border-slate-100 dark:border-slate-800/40">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-2.5">
                <SlidersHorizontal size={16} className="text-violet-500 dark:text-violet-400" />
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">Regional Filters</h3>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">Refine demand signals by tier, state, and category keyword</p>
                </div>
              </div>
              
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:w-auto w-full">
                {/* City Tier Dropdown */}
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-500 tracking-wider">City Tier</label>
                  <select
                    value={selectedTier}
                    onChange={(e) => setSelectedTier(e.target.value)}
                    className="text-xs font-semibold bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-violet-500 transition"
                  >
                    <option value="all">All Tiers</option>
                    <option value="tier1">Tier 1 Metros</option>
                    <option value="tier2">Tier 2 Growth Hubs</option>
                    <option value="tier3">Tier 3 Rural Districts</option>
                  </select>
                </div>

                {/* State Dropdown */}
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-500 tracking-wider">State / Territory</label>
                  <select
                    value={selectedState}
                    onChange={(e) => setSelectedState(e.target.value)}
                    className="text-xs font-semibold bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-violet-500 transition"
                  >
                    <option value="all">All States ({uniqueStates.length})</option>
                    {uniqueStates.map((st) => (
                      <option key={st} value={st}>{st}</option>
                    ))}
                  </select>
                </div>

                {/* Product Dropdown */}
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] uppercase font-bold text-slate-400 dark:text-slate-500 tracking-wider">Demand Keyword</label>
                  <select
                    value={selectedProduct}
                    onChange={(e) => setSelectedProduct(e.target.value)}
                    className="text-xs font-semibold bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-violet-500 transition"
                  >
                    <option value="all">All Keywords</option>
                    {activeProducts.map((p) => (
                      <option key={p.kw} value={p.kw}>{p.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          {/* ── Regional Highlights / Stats ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 animate-fade-in stagger-2">
            {/* Stat 1: Total signals */}
            <div className="glass rounded-xl p-4 border border-slate-100 dark:border-slate-800/40 relative overflow-hidden">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">Analyzed Centers</span>
              <div className="text-2xl font-black text-slate-950 dark:text-white mt-1">{filteredRegional.length}</div>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">Matching current active filters</p>
              <div className="absolute top-2 right-2 p-1.5 rounded-lg bg-violet-50 dark:bg-violet-900/10 text-violet-500 dark:text-violet-400">
                <Globe size={14} />
              </div>
            </div>

            {/* Stat 2: Top Growth Region */}
            <div className="glass rounded-xl p-4 border border-slate-100 dark:border-slate-800/40 relative overflow-hidden">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">Top Growth Market</span>
              <div className="text-base font-bold text-slate-900 dark:text-white mt-1 truncate">
                {topGrowthRegion ? `${topGrowthRegion.payload?.city}, ${topGrowthRegion.payload?.state}` : "—"}
              </div>
              <div className="flex items-center gap-1.5 mt-1.5">
                <TrendingUp size={12} className="text-emerald-500" />
                <span className="text-xs font-bold text-emerald-500 tabular-nums">
                  {topGrowthRegion ? `+${Math.round(Number(topGrowthRegion.normalized_score) * 100)}` : "0"} score
                </span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 truncate">
                  ({topGrowthRegion ? productMeta(industry, String(topGrowthRegion.payload?.product ?? "")).name || cleanLabel(topGrowthRegion.series_key) : "No data"})
                </span>
              </div>
            </div>

            {/* Stat 3: Coolest Market */}
            <div className="glass rounded-xl p-4 border border-slate-100 dark:border-slate-800/40 relative overflow-hidden">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">Coolest Market</span>
              <div className="text-base font-bold text-slate-900 dark:text-white mt-1 truncate">
                {coolestRegion ? `${coolestRegion.payload?.city}, ${coolestRegion.payload?.state}` : "—"}
              </div>
              <div className="flex items-center gap-1.5 mt-1.5">
                <TrendingDown size={12} className="text-rose-500" />
                <span className="text-xs font-bold text-rose-500 tabular-nums">
                  {coolestRegion ? `${Math.round(Number(coolestRegion.normalized_score) * 100)}` : "0"} score
                </span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 truncate">
                  ({coolestRegion ? productMeta(industry, String(coolestRegion.payload?.product ?? "")).name || cleanLabel(coolestRegion.series_key) : "No data"})
                </span>
              </div>
            </div>

            {/* Stat 4: Tier comparison */}
            <div className="glass rounded-xl p-4 border border-slate-100 dark:border-slate-800/40 relative overflow-hidden flex flex-col justify-between">
              <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                <span>Tier Performance</span>
                <span className="text-[9px] font-semibold text-slate-400 dark:text-slate-500 normal-case">Average Index</span>
              </div>
              
              <div className="space-y-1.5 mt-2">
                {/* Tier 1 */}
                <div>
                  <div className="flex justify-between text-[9px] font-bold text-slate-655 dark:text-slate-400 mb-0.5">
                    <span>Tier 1 (Metro)</span>
                    <span className={t1Avg >= 0 ? "text-emerald-500" : "text-rose-500"}>{t1Avg >= 0 ? "+" : ""}{t1Avg}%</span>
                  </div>
                  <div className="h-1 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className={clsx("h-full rounded-full", t1Avg >= 0 ? "bg-emerald-400" : "bg-rose-400")} style={{ width: `${Math.min(100, Math.abs(t1Avg))}%` }} />
                  </div>
                </div>

                {/* Tier 2 */}
                <div>
                  <div className="flex justify-between text-[9px] font-bold text-slate-655 dark:text-slate-400 mb-0.5">
                    <span>Tier 2 (Growth)</span>
                    <span className={t2Avg >= 0 ? "text-emerald-500" : "text-rose-500"}>{t2Avg >= 0 ? "+" : ""}{t2Avg}%</span>
                  </div>
                  <div className="h-1 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className={clsx("h-full rounded-full", t2Avg >= 0 ? "bg-emerald-400" : "bg-rose-400")} style={{ width: `${Math.min(100, Math.abs(t2Avg))}%` }} />
                  </div>
                </div>

                {/* Tier 3 */}
                <div>
                  <div className="flex justify-between text-[9px] font-bold text-slate-655 dark:text-slate-400 mb-0.5">
                    <span>Tier 3 (Rural)</span>
                    <span className={t3Avg >= 0 ? "text-emerald-500" : "text-rose-500"}>{t3Avg >= 0 ? "+" : ""}{t3Avg}%</span>
                  </div>
                  <div className="h-1 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className={clsx("h-full rounded-full", t3Avg >= 0 ? "bg-emerald-400" : "bg-rose-400")} style={{ width: `${Math.min(100, Math.abs(t3Avg))}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── Regional Cards Grid ── */}
          {filteredRegional.length === 0 ? (
            <div className="glass rounded-2xl p-12 text-center border border-slate-100 dark:border-slate-800/40">
              <MapPin size={32} className="mx-auto text-slate-350 dark:text-slate-650 mb-3" />
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">No regional centers found</h3>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 max-w-sm mx-auto">Try resetting or broadening your filters (Tier, State, or Keyword) to view active regional trends.</p>
              <Button
                size="sm"
                variant="secondary"
                className="mt-4 border border-slate-200 dark:border-slate-700 shadow-sm rounded-xl px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
                onClick={() => {
                  setSelectedTier("all");
                  setSelectedState("all");
                  setSelectedProduct("all");
                }}
              >
                Reset Filters
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 animate-fade-in stagger-3">
              {filteredRegional.map((s: any) => {
                const scoreVal = Number(s.normalized_score);
                const scorePct = Math.round(scoreVal * 100);
                const absPct = Math.min(100, Math.abs(scorePct));
                
                const tierName = String(s.payload?.tier || "TIER3").toUpperCase();
                const city = s.payload?.city || "Unknown Center";
                const state = s.payload?.state || "Unknown State";
                const keyword = s.payload?.product || cleanLabel(s.series_key);
                const category = s.payload?.category || "Category";
                
                const isPositive = scoreVal >= 0.05;
                const isNegative = scoreVal <= -0.05;
                const color = isPositive ? "#10b981" : isNegative ? "#ef4444" : "#94a3b8";
                const CardTrendIcon = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus;

                const tierStyle =
                  tierName === "TIER1"
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800/40"
                    : tierName === "TIER2"
                    ? "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800/40"
                    : "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40";

                return (
                  <div
                    key={s.id}
                    className="glass rounded-2xl p-5 border border-slate-100 dark:border-slate-800/40 shadow-md hover:shadow-lg hover:border-violet-500/30 dark:hover:border-violet-500/20 hover:-translate-y-0.5 transition-all duration-300 relative group overflow-hidden"
                  >
                    {/* Header info */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <MapPin size={12} className="text-slate-400 shrink-0" />
                          <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">{city}</h4>
                        </div>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium block mt-0.5">{state}</span>
                      </div>

                      <div className="flex flex-col items-end gap-1.5 shrink-0">
                        <span className={clsx("text-[9px] font-extrabold uppercase px-2 py-0.5 rounded-full border tracking-wide", tierStyle)}>
                          {tierName === "TIER1" ? "Tier 1 Metro" : tierName === "TIER2" ? "Tier 2 Growth" : "Tier 3 Rural"}
                        </span>
                      </div>
                    </div>

                    {/* Product Keyword Details */}
                    <div className="mt-4 p-2.5 rounded-xl bg-slate-50/50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-800/60 flex items-center justify-between">
                      <div className="min-w-0">
                        <span className="text-[9px] uppercase tracking-wider text-slate-400 dark:text-slate-500 font-extrabold block">Demand Center Target</span>
                        <span className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate capitalize">{keyword}</span>
                      </div>
                      <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-950 px-2 py-0.5 rounded-lg border border-slate-100 dark:border-slate-800 truncate shrink-0 max-w-[100px]">
                        {category}
                      </span>
                    </div>

                    {/* Diverging Visual Progress Gauge */}
                    <div className="mt-4">
                      <div className="flex items-center justify-between text-[10px] font-bold text-slate-450 dark:text-slate-500">
                        <span className="uppercase tracking-wider">Demand Score Range</span>
                        <span className="font-extrabold flex items-center gap-1" style={{ color }}>
                          <CardTrendIcon size={10} />
                          {scorePct >= 0 ? "+" : ""}{scorePct}%
                        </span>
                      </div>

                      {/* Diverging bar centred at 50% */}
                      <div className="relative h-2 rounded-full bg-slate-100 dark:bg-slate-700/60 overflow-hidden mt-1.5 border border-slate-200/20 dark:border-slate-800/10">
                        <div className="absolute top-0 left-1/2 w-px h-full bg-slate-350 dark:bg-slate-600 z-10" />
                        <div
                          className="absolute top-0 h-full rounded-full transition-all duration-700"
                          style={{
                            background: color,
                            width: `${absPct / 2}%`,
                            left: scoreVal >= 0 ? "50%" : `${50 - absPct / 2}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Meta info footer */}
                    <div className="flex items-center justify-between mt-5 pt-3 border-t border-slate-100 dark:border-slate-800/40 text-[9px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-wider">
                      <span className="flex items-center gap-1">
                        <span className="h-1 w-1 rounded-full bg-slate-400" />
                        {Math.round((s.confidence ?? 0.8) * 100)}% Confidence
                      </span>
                      <span>
                        Interest: {Math.round(s.raw_value ?? 0)}/100
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* State deep-dive modal */}
    </div>
  );
};
