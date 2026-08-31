import { useState, useMemo, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Play,
  Download,
  Sprout,
  Cpu,
  Shirt,
  Pill,
  Wrench,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart2,
  Layers,
  Clock,
  AlertCircle,
  CheckCircle2,
  Info,
  ChevronDown,
  ChevronUp,
  Sparkles,
  RefreshCw,
} from "@/components/ui/icons";
import toast from "react-hot-toast";
import clsx from "clsx";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { format, parseISO } from "date-fns";
import { forecastsApi } from "@/api/forecasts";
import { decisionsApi } from "@/api/decisions";
import { exportApi } from "@/api/export";
import { skusApi } from "@/api/skus";
import { Button } from "@/components/ui/Button";
import { ForecastConfidencePanel } from "@/components/charts/ForecastConfidencePanel";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { industryAccent, industryDisplay, industryGradient } from "@/utils/colors";
import { fmtCompact, fmtNumber } from "@/utils/format";
import type { ForecastResponse, ForecastRow, IndustryCode } from "@/types/api";
import type { Decision } from "@/api/decisions";

// ─────────────────────────────────────────────────────────────────────────────
// Industry config
// ─────────────────────────────────────────────────────────────────────────────
const INDUSTRY_ICONS: Record<IndustryCode, React.ReactNode> = {
  agrocenter: <Sprout size={18} />,
  electronics: <Cpu size={18} />,
  fashion: <Shirt size={18} />,
  pharma: <Pill size={18} />,
  hardware: <Wrench size={18} />,
};

const INDUSTRY_MODELS: Record<IndustryCode, { name: string; desc: string }[]> = {
  agrocenter: [
    { name: "TFT", desc: "Temporal Fusion Transformer — seasonal pattern capture" },
    { name: "Prophet+", desc: "Weather-adjusted Prophet with custom seasonality" },
    { name: "ARIMA-X", desc: "ARIMA with exogenous weather regressors" },
  ],
  electronics: [
    { name: "TFT", desc: "Temporal Fusion Transformer — long-range component signals" },
    { name: "LightGBM", desc: "Gradient boosting with supplier lead-time features" },
    { name: "N-BEATS", desc: "Neural basis expansion for trend decomposition" },
  ],
  fashion: [
    { name: "TFT", desc: "Temporal Fusion Transformer — trend-adjusted baseline" },
    { name: "DeepAR", desc: "Probabilistic RNN with social signal covariates" },
    { name: "Prophet+", desc: "Seasonality-aware with runway cycle calendar" },
  ],
  pharma: [
    { name: "Croston", desc: "Intermittent demand specialist for sparse SKUs" },
    { name: "TFT", desc: "Temporal Fusion Transformer — long-horizon GxP mode" },
    { name: "ETS", desc: "Exponential smoothing with regulatory event flags" },
  ],
  hardware: [
    { name: "TFT", desc: "Temporal Fusion Transformer — supplier lead-time aware" },
    { name: "LightGBM", desc: "Gradient boosting with commodity-price features" },
    { name: "N-HiTS", desc: "Neural hierarchical interpolation for steady demand" },
  ],
};

const INDUSTRY_HORIZON_HINT: Record<IndustryCode, string> = {
  agrocenter: "26w recommended — captures full planting-to-harvest cycle",
  electronics: "12–26w — aligns with component lead-time windows",
  fashion: "12w — matches seasonal sell-through planning cycle",
  pharma: "52w — GxP-compliant annual batch planning horizon",
  hardware: "16w recommended — covers supplier lead-time + project season",
};

const INDUSTRY_INSIGHT: Record<IndustryCode, (horizon: number) => { text: string; tone: "up" | "down" | "flat" }> = {
  agrocenter: (h) => ({ text: `Seasonal uplift expected in weeks 5–10 driven by pre-planting demand. ${h >= 26 ? "Full planting cycle captured." : "Consider extending to 26w for full cycle coverage."}`, tone: "up" }),
  electronics: (h) => ({ text: `Component lead-time risk elevated. Forecast band is wider than usual. ${h >= 16 ? "Supply chain window fully covered." : "Extend to 16w+ to cover full supply chain lag."}`, tone: "down" }),
  fashion: (h) => ({ text: `Trend momentum is strong — Q3 sell-through projected 12% above prior season. ${h >= 12 ? "Full season captured." : "12w horizon recommended for seasonal planning."}`, tone: "up" }),
  pharma: (h) => ({ text: `Demand stable with low volatility (P10–P90 band <8%). GxP batch planning horizon ${h >= 52 ? "is fully covered." : "should be extended to 52w for annual compliance."}`, tone: "flat" }),
  hardware: (h) => ({ text: `Commodity-cost pressure on steel & copper is widening the forecast band. ${h >= 16 ? "Supplier lead-time window fully covered." : "Extend to 16w+ to cover full supplier lead time."}`, tone: "up" }),
};



// ─────────────────────────────────────────────────────────────────────────────
// Horizon presets
// ─────────────────────────────────────────────────────────────────────────────
const HORIZON_PRESETS: Record<IndustryCode, { label: string; weeks: number; recommended?: boolean }[]> = {
  agrocenter: [
    { label: "8w", weeks: 8 },
    { label: "13w", weeks: 13 },
    { label: "26w", weeks: 26, recommended: true },
    { label: "52w", weeks: 52 },
  ],
  electronics: [
    { label: "4w", weeks: 4 },
    { label: "12w", weeks: 12, recommended: true },
    { label: "26w", weeks: 26 },
    { label: "52w", weeks: 52 },
  ],
  fashion: [
    { label: "4w", weeks: 4 },
    { label: "8w", weeks: 8 },
    { label: "12w", weeks: 12, recommended: true },
    { label: "26w", weeks: 26 },
  ],
  pharma: [
    { label: "13w", weeks: 13 },
    { label: "26w", weeks: 26 },
    { label: "52w", weeks: 52, recommended: true },
    { label: "104w", weeks: 104 },
  ],
  hardware: [
    { label: "8w", weeks: 8 },
    { label: "16w", weeks: 16, recommended: true },
    { label: "26w", weeks: 26 },
    { label: "52w", weeks: 52 },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** Optional explanation for planners who want to inspect the uncertainty model. */
function QuantileGuide({ accent }: { accent: string }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {[
        {
          label: "P10 — Conservative",
          badge: "Lower Bound",
          badgeCls: "bg-rose-50 text-rose-600 border-rose-200 dark:bg-rose-900/20 dark:text-rose-400 dark:border-rose-800/40",
          borderCls: "border-rose-200/70 dark:border-rose-800/40",
          bgCls: "bg-rose-50/30 dark:bg-rose-900/10",
          icon: <AlertCircle size={13} className="text-rose-500" />,
          iconBg: "bg-rose-100 dark:bg-rose-900/40",
          desc: "90% chance demand will exceed this. Use to avoid overstocking and free up working capital.",
          use: "Minimise excess stock",
          color: "#ef4444",
        },
        {
          label: "P50 — Expected",
          badge: "Most Likely",
          badgeCls: "border-violet-200 dark:border-violet-800/40",
          borderCls: "border-violet-200/70 dark:border-violet-800/40",
          bgCls: "bg-violet-50/30 dark:bg-violet-900/10",
          icon: <Sparkles size={13} className="text-violet-500" />,
          iconBg: "bg-violet-100 dark:bg-violet-900/40",
          desc: "The median forecast — equally likely to be higher or lower. Your baseline planning number.",
          use: "Day-to-day planning",
          color: accent,
        },
        {
          label: "P90 — Optimistic",
          badge: "Upper Bound",
          badgeCls: "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/40",
          borderCls: "border-emerald-200/70 dark:border-emerald-800/40",
          bgCls: "bg-emerald-50/30 dark:bg-emerald-900/10",
          icon: <CheckCircle2 size={13} className="text-emerald-500" />,
          iconBg: "bg-emerald-100 dark:bg-emerald-900/40",
          desc: "Only 10% chance demand exceeds this. Use to set safety stock so you're protected against demand spikes.",
          use: "Safety stock target",
          color: "#10b981",
        },
      ].map(({ label, badge, badgeCls, borderCls, bgCls, icon, iconBg, desc, use, color }) => (
        <div key={label} className={clsx("rounded-xl border p-4", borderCls, bgCls)}>
          <div className="flex items-center justify-between mb-3">
            <div className={clsx("h-7 w-7 rounded-lg flex items-center justify-center", iconBg)}>
              {icon}
            </div>
            <span className={clsx("text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border", badgeCls)}>
              {badge}
            </span>
          </div>
          <p className="text-xs font-bold text-slate-800 dark:text-slate-100 mb-1">{label}</p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">{desc}</p>
          <div className="mt-3 flex items-center gap-1.5">
            <div className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
            <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400">{use}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function buildIndicativeForecast(decisions: Decision[], horizon: number): ForecastResponse | null {
  const eligible = decisions
    .filter((decision) => decision.inputs.demand_p50_over_window > 0)
    .slice(0, 4);

  if (!eligible.length) return null;

  const start = new Date();
  const rows = eligible.flatMap((decision, skuIndex) => {
    const protectionWeeks = Math.max(1, decision.inputs.protection_days / 7);
    const weeklyBaseline = decision.inputs.demand_p50_over_window / protectionWeeks;

    return Array.from({ length: horizon }, (_, index) => {
      const date = new Date(start);
      date.setDate(start.getDate() + (index + 1) * 7);
      const progress = horizon <= 1 ? 0 : index / (horizon - 1);
      const direction = skuIndex % 3 === 1 ? -0.025 : skuIndex % 3 === 2 ? 0.03 : 0.08;
      const seasonalMovement = Math.sin((index + skuIndex) / 2.8) * 0.018;
      const expected = Math.max(0, weeklyBaseline * (1 + direction * progress + seasonalMovement));

      return {
        sku_id: decision.sku_id,
        forecast_date: date.toISOString().slice(0, 10),
        p10: Math.round(expected * 0.9),
        p50: Math.round(expected),
        p90: Math.round(expected * 1.1),
      };
    });
  });

  return {
    run_id: "indicative-decision-plan",
    n_predictions: rows.length,
    rows,
    source: "indicative",
    context_source: "current decision inputs",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Buy recommendation
// ─────────────────────────────────────────────────────────────────────────────
function getBuyRecommendation(rows: ForecastRow[]) {
  const p50s = rows.map((r) => r.p50);
  const p90s = rows.map((r) => r.p90);
  const p10s = rows.map((r) => r.p10);
  const avgP50 = p50s.reduce((a, b) => a + b, 0) / (p50s.length || 1);
  const trend = p50s[p50s.length - 1] - p50s[0];
  const trendPct = (trend / (p50s[0] || 1)) * 100;
  const uncertaintyRatio = (Math.max(...p90s) - Math.min(...p10s)) / (avgP50 || 1);

  const rising  = trendPct > 5;
  const falling = trendPct < -5;
  const wideband = uncertaintyRatio > 0.45;

  if (rising && wideband) {
    return {
      badge: "Buy now — and stock up",
      badgeCls: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800/40",
      dotCls: "bg-amber-400",
      message: "Demand is rising and the forecast band is wide — stockout risk is elevated. Increase safety stock above normal reorder levels.",
    };
  }
  if (rising) {
    return {
      badge: "Yes — buy now",
      badgeCls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/40",
      dotCls: "bg-emerald-500",
      message: "Demand is trending up over the forecast window. Place purchase orders now to cover projected growth.",
    };
  }
  if (falling) {
    return {
      badge: "No purchase needed",
      badgeCls: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-400 dark:border-rose-800/40",
      dotCls: "bg-rose-500",
      message: "Demand is projected to decline. Hold current stock and avoid over-ordering to prevent excess inventory.",
    };
  }
  return {
    badge: "Maintain current levels",
    badgeCls: "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800/40 dark:text-slate-400 dark:border-slate-700/40",
    dotCls: "bg-slate-400",
    message: "Demand is stable. Replenish at your normal reorder point — no urgent action needed.",
  };
}

/** Single SKU forecast chart with one clear demand line and a restrained range. */
function SkuForecastChart({
  skuId,
  skuCode,
  skuLabel,
  rows,
  accent,
}: {
  skuId: string;
  skuCode?: string;
  skuLabel: string;
  rows: ForecastRow[];
  accent: string;
}) {
  const [expanded, setExpanded] = useState(false);

  const chartData = rows.map((r) => ({
    date: r.forecast_date,
    p10: r.p10,
    p50: r.p50,
    p90: r.p90,
    band: [r.p10, r.p90] as [number, number],
  }));

  const p50Values = rows.map((r) => r.p50);
  const maxP50 = Math.max(...p50Values);
  const minP50 = Math.min(...p50Values);
  const trend = p50Values[p50Values.length - 1] - p50Values[0];
  const trendPct = ((trend / (p50Values[0] || 1)) * 100).toFixed(1);
  const isUp = trend > 0;
  const TrendIcon = trend > p50Values[0] * 0.02 ? TrendingUp : trend < -p50Values[0] * 0.02 ? TrendingDown : Minus;
  const trendColor = isUp ? "text-emerald-600 dark:text-emerald-400" : trend < 0 ? "text-rose-500 dark:text-rose-400" : "text-slate-400";

  const displayHeight = expanded ? 300 : 200;
  const rec = getBuyRecommendation(rows);

  return (
    <div className="glass rounded-2xl overflow-hidden card-hover-premium">
      {/* Header */}
      <div className="p-4 border-b border-slate-100/80 dark:border-slate-700/40">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-[10px] font-bold bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40">
                {skuCode || skuId}
              </span>
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 truncate">
                {skuLabel}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1.5 text-[10px] text-slate-500 dark:text-slate-400">
              <span className="flex items-center gap-1">
                <span className="font-semibold text-slate-700 dark:text-slate-200">{rows.length}</span> weeks
              </span>
              <span>·</span>
              <span>Peak P50 <strong className="text-slate-700 dark:text-slate-200">{fmtCompact(maxP50)}</strong></span>
              <span>·</span>
              <span>Floor <strong className="text-slate-700 dark:text-slate-200">{fmtCompact(minP50)}</strong></span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className={clsx("flex items-center gap-1 text-[10px] font-bold", trendColor)}>
              <TrendIcon size={12} />
              {isUp ? "+" : ""}{trendPct}%
            </div>
            <button
              onClick={() => setExpanded(!expanded)}
              className="h-6 w-6 rounded-lg bg-slate-100 dark:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        <ResponsiveContainer width="100%" height={displayHeight}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="2 6" stroke="var(--line)" />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => format(parseISO(d), "MMM d")}
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
              interval={Math.max(1, Math.floor(rows.length / 6))}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => fmtCompact(v)}
              domain={[
                (dataMin: number) => Math.max(0, Math.floor(dataMin * 0.9)),
                (dataMax: number) => Math.ceil(dataMax * 1.1),
              ]}
            />
            <Tooltip
              contentStyle={{
                background: "#fff",
                border: "1px solid #e2e8f0",
                borderRadius: 10,
                fontSize: 11,
                boxShadow: "0 4px 20px rgba(15,23,42,0.08)",
              }}
              labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = { p10: "P10 (Conservative)", p50: "P50 (Expected)", p90: "P90 (Optimistic)" };
                return [fmtNumber(value), labels[name] ?? name];
              }}
            />
            {/* Today reference line */}
            <ReferenceLine
              x={new Date().toISOString().slice(0, 10)}
              stroke="#94a3b8"
              strokeDasharray="4 4"
              label={{ value: "Today", position: "top", fontSize: 9, fill: "#94a3b8" }}
            />
            {/* Uncertainty band */}
            <Area
              type="linear"
              dataKey="band"
              stroke="none"
              fill={accent}
              fillOpacity={0.1}
              isAnimationActive={false}
              name="Expected range"
            />
            {/* P50 median — bold */}
            <Line
              type="linear"
              dataKey="p50"
              stroke={accent}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Expected demand"
            />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="mt-2 flex flex-wrap items-center gap-5 text-[11px] text-content-muted">
          <span className="inline-flex items-center gap-2"><span className="h-0.5 w-7 rounded-full" style={{ background: accent }} />Expected demand</span>
          <span className="inline-flex items-center gap-2"><span className="h-3 w-7 rounded-sm" style={{ background: accent, opacity: 0.1 }} />Expected range</span>
          <span className="ml-auto text-content-subtle">Hover for low, expected, and high values</span>
        </div>

      </div>

      {/* ── AI Buy Recommendation ── */}
      <div className="border-t border-slate-100/80 dark:border-slate-700/40 px-4 py-3 flex items-start gap-3">
        <div className={clsx("h-2 w-2 rounded-full mt-1.5 shrink-0 animate-pulse", rec.dotCls)} />
        <div className="flex-1 min-w-0">
          <span className={clsx("inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border mb-1.5", rec.badgeCls)}>
            {rec.badge}
          </span>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">{rec.message}</p>
        </div>
      </div>
    </div>
  );
}

/** Summary stat card */
function SummaryCard({
  label,
  value,
  sub,
  icon,
  tone = "default",
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  tone?: "default" | "up" | "down";
}) {
  const iconBg = tone === "up" ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400" :
    tone === "down" ? "bg-rose-50 dark:bg-rose-900/20 text-rose-500 dark:text-rose-400" :
    "bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400";

  return (
    <div className="glass rounded-2xl p-5 card-hover-premium">
      <div className="flex items-center gap-3 mb-3">
        <div className={clsx("h-9 w-9 rounded-xl flex items-center justify-center shrink-0", iconBg)}>
          {icon}
        </div>
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">{label}</span>
      </div>
      <div className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">{value}</div>
      <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 font-medium">{sub}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SKU label lookup per industry
// ─────────────────────────────────────────────────────────────────────────────
const SKU_LABELS: Record<string, string> = {
  "AGR-FERT-001": "Urea Fertilizer 50kg",
  "AGR-SEED-012": "Hybrid Corn Seeds 20kg",
  "AGR-PEST-007": "Herbicide 1L",
  "AGR-IRRI-003": "Drip Irrigation Kit",
  "ELC-PHN-001": "Flagship Smartphone",
  "ELC-LAP-003": "Ultra Laptop 14in",
  "ELC-AUD-008": "Noise-Cancel Earbuds",
  "ELC-SHM-002": "Smart Home Hub",
  "FSH-WOM-001": "Women's Blazer — SS26",
  "FSH-MEN-004": "Men's Chino Trousers",
  "FSH-SHO-011": "Platform Sneakers",
  "FSH-ACC-006": "Woven Tote Bag",
  "PHA-ONC-001": "Oncology API — Batch C",
  "PHA-ALL-007": "Antihistamine Tabs 30ct",
  "PHA-INS-002": "Insulin Vials 10mL",
  "PHA-ANT-009": "Broad-Spectrum Antibiotic",
};

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
export const ForecastsPage = () => {
  const industry = useWorkspaceIndustry();
  const accent = industryAccent[industry];
  const gradient = industryGradient[industry];
  const displayName = industryDisplay[industry];
  const icon = INDUSTRY_ICONS[industry];
  const models = INDUSTRY_MODELS[industry];
  const presets = HORIZON_PRESETS[industry];
  const defaultHorizon = presets.find((p) => p.recommended)?.weeks ?? presets[1].weeks;

  const [horizon, setHorizon] = useState(defaultHorizon);
  const [result, setResult] = useState<ForecastResponse | null>(null);

  // Fetch SKUs for mapping ID to code and name/description
  const { data: skus = [] } = useQuery({
    queryKey: ["skus"],
    queryFn: () => skusApi.list({ limit: 1000 }),
  });

  const { data: decisionData } = useQuery({
    queryKey: ["decisions", industry, "open", "forecast-fallback"],
    queryFn: () => decisionsApi.list({ status: "open", limit: 20 }),
    staleTime: 60_000,
  });

  const skuLookup = useMemo(() => {
    const map = new Map<string, { code: string; name: string }>();
    skus.forEach((s) => {
      map.set(s.id, {
        code: s.sku_code,
        name: s.description || s.sku_code,
      });
    });
    return map;
  }, [skus]);

  const run = useMutation({
    mutationFn: () =>
      forecastsApi.generate({ horizon, force_zero_shot: true }),
    onSuccess: (r) => {
      setResult(r);
    },
    onError: () => {
      setResult(null);
    },
  });

  // Auto-generate forecast on mount and when industry/horizon changes.
  useEffect(() => {
    run.mutate();
  }, [industry, horizon]);

  const indicativeResult = useMemo(
    () => buildIndicativeForecast(decisionData?.decisions ?? [], horizon),
    [decisionData?.decisions, horizon],
  );
  const currentResult = result?.rows.length ? result : indicativeResult;
  const isIndicative = currentResult?.source === "indicative";
  const insight = INDUSTRY_INSIGHT[industry](horizon);
  const DirIcon = insight.tone === "up" ? TrendingUp : insight.tone === "down" ? TrendingDown : Minus;

  // Group rows by sku_id
  const grouped = useMemo(() => {
    if (!currentResult) return [];
    const map = new Map<string, ForecastRow[]>();
    currentResult.rows.forEach((r) => {
      const list = map.get(r.sku_id) ?? [];
      list.push(r);
      map.set(r.sku_id, list);
    });
    return Array.from(map.entries()).slice(0, 4);
  }, [currentResult]);

  const handleHorizonChange = (w: number) => {
    setHorizon(w);
  };

  return (
    <div className="space-y-4 animate-fade-in" data-industry={industry}>

      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          {/* Industry pill */}
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold text-white mb-3"
            style={{ background: gradient }}
          >
            {icon} {displayName}
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Demand Forecasts
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-xl leading-relaxed">
            Expected demand by SKU, with a restrained range showing likely variation. Start with the recommendation; open settings only when you need them.
          </p>
        </div>

        {/* Export buttons — shown when result exists */}
        {currentResult && !isIndicative && (
          <div className="flex items-center gap-2 shrink-0">

            <button
              onClick={() => exportApi.forecastXlsx(industry).catch(() => toast.error("Export failed"))}
              className="tactile-press flex items-center gap-1.5 text-xs font-bold px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition glass"
            >
              <Download size={13} /> Excel
            </button>
            <button
              onClick={() => exportApi.signalsCsv(industry).catch(() => toast.error("Export failed"))}
              className="tactile-press flex items-center gap-1.5 text-xs font-bold px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition glass"
            >
              <Download size={13} /> Signals CSV
            </button>
          </div>
        )}
      </div>

      {/* ── Insight Banner ── */}
      {currentResult && (
        <div
          className={clsx(
            "flex items-center gap-4 p-4 rounded-2xl border",
            insight.tone === "up"
              ? "bg-emerald-50/60 border-emerald-200/80 dark:bg-emerald-900/15 dark:border-emerald-800/40"
              : insight.tone === "down"
              ? "bg-rose-50/60 border-rose-200/80 dark:bg-rose-900/15 dark:border-rose-800/40"
              : "bg-slate-50/80 border-slate-200/60 dark:bg-slate-800/30 dark:border-slate-700/40"
          )}
        >
          <div
            className={clsx(
              "h-10 w-10 rounded-xl flex items-center justify-center shrink-0",
              insight.tone === "up" ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400" :
              insight.tone === "down" ? "bg-rose-100 dark:bg-rose-900/40 text-rose-500 dark:text-rose-400" :
              "bg-slate-100 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400"
            )}
          >
            <DirIcon size={18} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug">{insight.text}</p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
              {isIndicative ? "Indicative plan from current decision inputs" : `Live ensemble · ${models.map((m) => m.name).join(", ")}`} · <strong className="text-slate-700 dark:text-slate-200">{horizon} weeks</strong> · <strong className="text-slate-700 dark:text-slate-200">{displayName}</strong>
            </p>
          </div>
          {isIndicative && <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:border-amber-800/60 dark:bg-amber-900/20 dark:text-amber-300">Live engine unavailable</span>}
        </div>
      )}

      {/* ── Configure Run ── */}
      <details className="group rounded-2xl border border-line bg-surface px-5 py-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
          <span><span className="flex items-center gap-2 text-sm font-semibold text-content"><BarChart2 size={15} className="text-[var(--accent)]" />Forecast settings</span><span className="mt-1 block text-xs text-content-muted">{horizon} weeks · {models.map((model) => model.name).join(", ")}</span></span>
          <ChevronDown size={16} className="text-content-subtle transition group-open:rotate-180" />
        </summary>
        <div className="mt-5 space-y-5 border-t border-line pt-4">
          {/* Horizon selector */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                Forecast Horizon
              </label>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 italic">
                {INDUSTRY_HORIZON_HINT[industry]}
              </span>
            </div>
            <div className="flex gap-2 flex-wrap">
              {presets.map(({ label, weeks, recommended }) => (
                <button
                  key={weeks}
                  onClick={() => handleHorizonChange(weeks)}
                  className={clsx(
                    "relative px-4 py-2 rounded-xl text-sm font-bold border transition-all duration-200 tactile-press",
                    horizon === weeks
                      ? "text-white border-transparent shadow-md"
                      : "bg-white dark:bg-slate-800/60 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600"
                  )}
                  style={horizon === weeks ? { background: gradient } : {}}
                >
                  {label}
                  {recommended && (
                    <span className="absolute -top-1.5 -right-1.5 text-[8px] font-black bg-amber-400 text-white px-1 py-0.5 rounded-full leading-none">
                      REC
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Active models */}
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 block mb-2">
              Active Model Ensemble
            </label>
            <div className="flex gap-2 flex-wrap">
              {models.map(({ name, desc }) => (
                <div
                  key={name}
                  title={desc}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 text-xs font-semibold text-slate-700 dark:text-slate-200"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  {name}
                </div>
              ))}
            </div>
          </div>

          {/* Generate button */}
          <div className="flex items-center gap-3 pt-1">
            <Button
              icon={run.isPending ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
              loading={run.isPending}
              onClick={() => run.mutate()}
              className="btn-primary tactile-press px-6 py-2.5 font-semibold"
            >
              {run.isPending ? "Generating…" : "Generate Live Forecast"}
            </Button>

          </div>
        </div>
      </details>

      {/* ── Progressive disclosure keeps model terminology out of the main task. ── */}
      <details className="group rounded-xl border border-line bg-surface px-4 py-3">
        <summary className="flex cursor-pointer list-none items-center justify-between text-xs font-semibold text-content-muted">
          <span className="flex items-center gap-2"><Info size={13} />How uncertainty is shown</span>
          <ChevronDown size={15} className="transition group-open:rotate-180" />
        </summary>
        <div className="mt-4 border-t border-line pt-4"><QuantileGuide accent={accent} /></div>
      </details>

      {/* ── Results ── */}
      {!currentResult ? (
        <div className="glass rounded-2xl p-16 text-center">
          <BarChart2 size={32} className="mx-auto text-slate-300 dark:text-slate-600 mb-3 animate-pulse" />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No Forecast Run Executed Yet</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Configure your horizon above and click "Generate Live Forecast" to run the ensemble models.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <SummaryCard
              label="SKUs Forecasted"
              value={fmtCompact(grouped.length)}
              sub="Active products in scope"
              icon={<Layers size={16} />}
            />
            <SummaryCard
              label="Forecast Rows"
              value={fmtCompact(currentResult.n_predictions)}
              sub="Total quantile data points"
              icon={<BarChart2 size={16} />}
            />
            <SummaryCard
              label="Horizon"
              value={`${horizon}w`}
              sub="Weeks of forward coverage"
              icon={<Clock size={16} />}
            />
            <SummaryCard
              label="Trend Signal"
              value={insight.tone === "up" ? "↑ Positive" : insight.tone === "down" ? "↓ Caution" : "→ Stable"}
              sub="Overall demand direction"
              icon={<DirIcon size={16} />}
              tone={insight.tone === "up" ? "up" : insight.tone === "down" ? "down" : "default"}
            />
          </div>

          {/* Per-SKU Charts */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="h-px flex-1 bg-slate-100 dark:bg-slate-800/60" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 px-3">
                Expected demand by SKU
              </span>
              <div className="h-px flex-1 bg-slate-100 dark:bg-slate-800/60" />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {grouped.map(([skuId, rows]) => {
                const skuInfo = skuLookup.get(skuId);
                const codeToShow = skuInfo?.code || skuId;
                const labelToShow = skuInfo?.name || SKU_LABELS[codeToShow] || codeToShow;
                return (
                  <SkuForecastChart
                    key={skuId}
                    skuId={skuId}
                    skuCode={codeToShow !== skuId ? codeToShow : undefined}
                    skuLabel={labelToShow}
                    rows={rows}
                    accent={accent}
                  />
                );
              })}
            </div>
          </div>

          {/* The confidence drill-down follows the forecast itself, so the
              planner sees the answer before the model diagnostics. */}
          <ForecastConfidencePanel />
        </div>
      )}
    </div>
  );
};
