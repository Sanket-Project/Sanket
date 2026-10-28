import { useState, useMemo, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { exportApi } from "@/api/export";
import { forecastsApi } from "@/api/forecasts";
import { locationsApi } from "@/api/locations";
import { Button } from "@/components/ui/Button";
import { ForecastConfidencePanel } from "@/components/charts/ForecastConfidencePanel";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getErrorMessage } from "@/utils/errors";
import { usePersistedForecast } from "@/hooks/usePersistedForecast";
import { ForecastRunStatus } from "@/components/charts/ForecastRunStatus";
import { SKUS_PER_PAGE, describeSource, omissionReason } from "@/utils/forecastPresentation";
import { industryAccent, industryDisplay, industryGradient } from "@/utils/colors";
import { fmtCompact, fmtNumber } from "@/utils/format";
import type { ForecastRow, IndustryCode } from "@/types/api";
import { periodProjectionApi } from "@/api/periodProjection";
import { AverageSalesProjection } from "@/components/charts/AverageSalesProjection";
import { PageLoader } from "@/components/ui/Spinner";
import { useAuthStore } from "@/stores/auth";

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

const INDUSTRY_HORIZON_HINT: Record<IndustryCode, string> = {
  agrocenter: "26w recommended — captures full planting-to-harvest cycle",
  electronics: "12–26w — aligns with component lead-time windows",
  fashion: "12w — matches seasonal sell-through planning cycle",
  pharma: "52w — GxP-compliant annual batch planning horizon",
  hardware: "16w recommended — covers supplier lead-time + project season",
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

// ─────────────────────────────────────────────────────────────────────────────
// Forecast shape summary (ordering also requires inventory and lead times).
// ─────────────────────────────────────────────────────────────────────────────
function getForecastSummary(rows: ForecastRow[]) {
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
      badge: "Projected demand rising · wide range",
      badgeCls: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800/40",
      dotCls: "bg-amber-400",
      message: "The median forecast rises across this window, with a wide forecast range. Review stock coverage and lead times in Decisions before choosing an order.",
    };
  }
  if (rising) {
    return {
      badge: "Projected demand rising",
      badgeCls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800/40",
      dotCls: "bg-emerald-500",
      message: "The median forecast rises across this window. Review stock coverage and lead times in Decisions before choosing an order.",
    };
  }
  if (falling) {
    return {
      badge: "Projected demand falling",
      badgeCls: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-400 dark:border-rose-800/40",
      dotCls: "bg-rose-500",
      message: "The median forecast falls across this window. Ordering needs also depend on stock coverage and lead times; review Decisions.",
    };
  }
  return {
    badge: "Projected median broadly flat",
    badgeCls: "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800/40 dark:text-slate-400 dark:border-slate-700/40",
    dotCls: "bg-slate-400",
    message: "The median forecast changes little across this window. This does not establish whether stock is sufficient; review coverage and lead times in Decisions.",
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
  const rec = getForecastSummary(rows);

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
function LocationForecastView({ skuId, runId }: { skuId: string; runId: string | undefined }) {
  const [location, setLocation] = useState("");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["location-forecast", skuId, runId], queryFn: () => locationsApi.forecast(skuId, runId),
  });
  if (isLoading) return <p>Loading location forecast…</p>;
  if (isError) return <p role="alert">Location forecast could not be loaded.</p>;
  if (!data) return null;
  return <div className="space-y-3">
    {data.locations.length > 0 && <select aria-label="Forecast location" value={location}
      onChange={(e) => setLocation(e.target.value)} className="rounded-lg border border-line bg-surface px-3 py-2 text-sm">
      <option value="">All locations</option>{data.locations.map((loc) => <option key={loc.location_id} value={loc.code}>{loc.name}</option>)}
    </select>}
    {data.degraded && <p className="text-sm text-amber-700" role="status">
      Location split incomplete: {data.unassigned_share == null ? "Unknown" : Math.round(data.unassigned_share * 100)}% of sales have no location
    </p>}
    {!data.locations.length ? <p>{data.reason}</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm">
      <caption className="sr-only">Expected units per location and forecast week. Exact values include the uncertainty range.</caption>
      <thead><tr><th className="p-2">Location</th>{Array.from({ length: Math.max(...data.locations.map((l) => l.p50.length)) }, (_, i) =>
        <th key={i} className="p-2">{data.locations[0]?.forecast_dates?.[i] ? format(parseISO(data.locations[0].forecast_dates[i]), "d MMM yyyy") : `Week ${i + 1}`}</th>)}</tr></thead>
      <tbody>{data.locations.filter((loc) => !location || loc.code === location).map((loc) => <tr key={loc.location_id} className="border-t border-line">
        <th scope="row" className="p-2">{loc.name}</th>{loc.p50.map((p50, i) =>
          <td key={i} className="p-2 tabular-nums" title={`P10 ${loc.p10[i]} – P90 ${loc.p90[i]}`}><span aria-label={`${p50.toLocaleString()} expected units; uncertainty range ${loc.p10[i].toLocaleString()} to ${loc.p90[i].toLocaleString()} units`}>{p50.toLocaleString()} units</span><span className="sr-only">, range {loc.p10[i].toLocaleString()} to {loc.p90[i].toLocaleString()} units</span></td>)}
      </tr>)}</tbody>
    </table></div>}
  </div>;
}

export const ForecastsPage = () => {
  const industry = useWorkspaceIndustry();
  const tenant = useAuthStore(s => s.tenantId);
  return <ForecastMethods key={`${tenant}:${industry}`} />;
};

function ForecastMethods() {
  const industry = useWorkspaceIndustry();
  const tenant = useAuthStore(s => s.tenantId);
  const [method, setMethod] = useState<"average" | "model" | null>(null);
  const query = useQuery({ queryKey: ["average-sales", tenant, industry, "availability"],
    queryFn: () => periodProjectionApi.get({ limit: 1 }), retry: false });
  if (query.isLoading) return <PageLoader />;
  if (query.isError && method !== "model") return <div role="alert" className="space-y-4 rounded-xl border border-line p-5 text-content"><p>Forecast methods could not be loaded.</p><Button onClick={() => void query.refetch()}>Retry methods</Button><Button variant="secondary" onClick={() => setMethod("model")}>Open Chronos model</Button></div>;
  if (query.data?.status !== "available") return <ChronosForecastPage />;
  return <div className="space-y-5"><div className="flex flex-wrap gap-2" aria-label="Forecast method">
    <Button variant={method !== "model" ? "primary" : "secondary"} aria-pressed={method !== "model"} onClick={() => setMethod("average")}>Average-sales projection</Button>
    <Button variant={method === "model" ? "primary" : "secondary"} aria-pressed={method === "model"} onClick={() => setMethod("model")}>Chronos model</Button>
  </div>{method === "model" ? <ChronosForecastPage /> : <AverageSalesProjection />}</div>;
}

const ChronosForecastPage = () => {
  const industry = useWorkspaceIndustry();
  const accent = industryAccent[industry];
  const gradient = industryGradient[industry];
  const displayName = industryDisplay[industry];
  const icon = INDUSTRY_ICONS[industry];
  const presets = HORIZON_PRESETS[industry];
  const defaultHorizon = presets.find((p) => p.recommended)?.weeks ?? presets[1].weeks;

  const [horizon, setHorizon] = useState(defaultHorizon);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [locationSku, setLocationSku] = useState("");
  const [locationSearch, setLocationSearch] = useState("");
  const [pageRun, setPageRun] = useState<string | undefined>();
  const run = usePersistedForecast({ horizon, offset: page * SKUS_PER_PAGE, search, runId: page ? pageRun : undefined });
  const locationCatalog = useQuery({
    queryKey: ["forecast-location-skus", industry, locationSearch],
    queryFn: () => forecastsApi.latest({ view: "skus", limit: 100, search: locationSearch }),
    retry: false,
  });
  const result = run.data;
  const currentResult = result;
  const source = describeSource(result?.source);
  const runError = run.isError ? getErrorMessage(run.error, "Saved forecast could not be loaded.") : null;
  const omitted = result?.omitted ?? [];
  const skuLookup = useMemo(() => new Map(Object.entries(result?.sku_labels ?? {})), [result?.sku_labels]);
  const locationSkuLookup = useMemo(() => new Map(Object.entries(locationCatalog.data?.forecast?.sku_labels ?? {})), [locationCatalog.data?.forecast?.sku_labels]);
  const totalSkus = result?.total_skus ?? 0;
  const actualHorizon = result?.horizon_weeks;
  const completedRun = run.refreshStatus?.status === "completed" ? run.refreshStatus.base_run_id : null;
  const refreshId = run.refreshStatus?.id;
  const refreshState = run.refreshStatus?.status;
  const observedActiveRefresh = useRef<string | undefined>();
  useEffect(() => {
    if (refreshState === "pending" || refreshState === "running") {
      observedActiveRefresh.current = refreshId;
    } else if (refreshState === "completed") {
      const justCompleted = refreshId === observedActiveRefresh.current;
      observedActiveRefresh.current = undefined;
      if (justCompleted && page > 0 && completedRun && pageRun && completedRun !== pageRun) {
        setPage(0);
        setPageRun(undefined);
        setLocationSku("");
      }
    } else if (refreshState === "failed") {
      observedActiveRefresh.current = undefined;
    }
  }, [page, pageRun, completedRun, refreshId, refreshState]);

  // Group rows by sku_id
  const grouped = useMemo(() => {
    if (!currentResult) return [];
    const map = new Map<string, ForecastRow[]>();
    currentResult.rows.forEach((r) => {
      const list = map.get(r.sku_id) ?? [];
      list.push(r);
      map.set(r.sku_id, list);
    });
    // Every SKU in the response, in a stable order; the page shows them in pages.
    return Array.from(map.entries()).sort(([a], [b]) => {
      const ca = skuLookup.get(a)?.code ?? a;
      const cb = skuLookup.get(b)?.code ?? b;
      return ca.localeCompare(cb, undefined, { numeric: true });
    });
  }, [currentResult, skuLookup]);
  const pageCount = Math.max(1, Math.ceil(totalSkus / SKUS_PER_PAGE));
  const pageStart = page * SKUS_PER_PAGE;
  const visible = grouped;

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
        {currentResult && (
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

      <ForecastRunStatus forecast={result} stale={run.stale} refreshing={run.refreshing} generating={run.generating} queued={run.refreshStatus?.status === "pending"} waitingForOtherIndustry={run.waitingForOtherIndustry} error={run.refreshError} />
      {(run.refreshError || runError) && <Button variant="secondary" onClick={() => { void run.refetch(); run.requestRefresh(); }}>Retry forecast</Button>}
      {/* ── Error: say what the service said, never a blank page ── */}
      {runError && (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50/70 p-4 text-sm text-rose-800 dark:border-rose-800/50 dark:bg-rose-900/15 dark:text-rose-200">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">Saved forecast could not be loaded</p>
            <p className="mt-0.5">{runError}</p>
          </div>
        </div>
      )}

      {/* ── What produced this result (from the response, never assumed) ── */}
      {currentResult && (
        <div className="flex items-start gap-4 p-4 rounded-2xl border bg-slate-50/80 border-slate-200/60 dark:bg-slate-800/30 dark:border-slate-700/40">
          <div className="h-10 w-10 rounded-xl flex items-center justify-center shrink-0 bg-slate-100 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400">
            <Info size={18} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug">
              {source.short} · Saved forecast: {actualHorizon} weeks · {displayName}
            </p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">{source.detail}</p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
              {result?.source === "hybrid-trend-fused" ? "Trend-adjusted forecast from a completed Hybrid run." : "No external signals applied to this forecast — trend and signal adjustment happen only in Hybrid forecasts."}
              {result?.history_end ? ` History used: complete weeks before ${result.history_end} (weeks start Monday, UTC).` : ""}
            </p>
          </div>
        </div>
      )}

      {/* ── Configure Run ── */}
      <details className="group rounded-2xl border border-line bg-surface px-5 py-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
          <span><span className="flex items-center gap-2 text-sm font-semibold text-content"><BarChart2 size={15} className="text-[var(--accent)]" />Forecast settings</span><span className="mt-1 block text-xs text-content-muted">{horizon} weeks · {result ? source.short : "Chronos zero-shot (pretrained model)"}</span></span>
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

          {/* The model this page runs, stated plainly */}
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 block mb-2">
              Model
            </label>
            <p className="text-xs text-content-muted max-w-xl">
              {describeSource(result?.source ?? "chronos_zero_shot").detail}
            </p>
          </div>

          {/* Generate button */}
          <div className="flex items-center gap-3 pt-1">
            <Button
              icon={run.refreshing ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
              loading={run.refreshing}
              onClick={() => { setPage(0); setPageRun(undefined); run.requestRefresh(); }}
              className="btn-primary tactile-press px-6 py-2.5 font-semibold"
            >
              {run.refreshing ? "Refreshing…" : "Refresh forecast"}
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
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No forecast to display</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Import sufficient sales history, then use Refresh forecast to generate a real forecast.</p>
        </div>
      ) : (
        <div className="space-y-5">
          <p className="text-sm text-content-muted">
            Chronos has not been shown to beat simple baselines on every SKU. Validate forecasts
            against your own sales before relying on them.
          </p>
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <SummaryCard
              label="SKUs forecast"
              value={`${fmtCompact(totalSkus)} SKUs forecast`}
              sub="SKUs in the saved run"
              icon={<Layers size={16} />}
            />
            <SummaryCard
              label="Not forecast"
              value={result?.omitted_count == null ? "Unknown" : fmtCompact(result.omitted_count)}
              sub={result?.omitted_count == null ? "Coverage was not recorded for this run" : result.omitted_count ? "See recorded omissions below" : "No omissions recorded"}
              icon={<AlertCircle size={16} />}
            />
            <SummaryCard
              label="Horizon"
              value={`${actualHorizon}w`}
              sub="Saved forecast horizon"
              icon={<Clock size={16} />}
            />
            <SummaryCard
              label="Model"
              value={source.short}
              sub={source.isModel ? "As reported by the forecast service" : "Not a model forecast"}
              icon={<BarChart2 size={16} />}
            />
          </div>

          {/* Per-SKU Charts */}
          {<div className="rounded-2xl border border-line bg-surface p-4 space-y-3">
            <h2 className="font-heading font-semibold">By location</h2>
            <label className="block text-xs font-semibold text-content-muted">Find a SKU
              <input aria-label="Location forecast SKU search" type="search" value={locationSearch} onChange={(e) => setLocationSearch(e.target.value)}
                placeholder="Search product or SKU" className="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm" />
            </label>
            <select aria-label="Location forecast SKU" value={locationSku} onChange={(e) => setLocationSku(e.target.value)}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-sm">
              <option value="">Choose SKU</option>{Array.from(locationSkuLookup.entries()).map(([id, label]) => <option key={id} value={id}>{label.code} · {label.name}</option>)}
            </select>
            {locationSku && <LocationForecastView skuId={locationSku} runId={result?.run_id} />}
          </div>}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="h-px flex-1 bg-slate-100 dark:bg-slate-800/60" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 px-3">
                Expected demand by SKU
              </span>
              <div className="h-px flex-1 bg-slate-100 dark:bg-slate-800/60" />
            </div>
            <label className="mb-3 block max-w-md text-xs font-semibold text-content-muted">Search forecasts
              <input aria-label="Search forecasts" type="search" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); setPageRun(undefined); }}
                placeholder="Product name or SKU" className="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm" />
            </label>
            <div className="mb-3 flex items-center justify-between text-xs text-content-muted">
              <span>
                Showing {grouped.length ? pageStart + 1 : 0}–{Math.min(pageStart + SKUS_PER_PAGE, totalSkus)} of {totalSkus} SKUs
              </span>
              {pageCount > 1 && (
                <span className="flex items-center gap-2">
                  <button type="button" aria-label="Previous page" disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    className="rounded-lg border border-line px-2 py-1 disabled:opacity-40">Previous</button>
                  <span>Page {page + 1} of {pageCount}</span>
                  <button type="button" aria-label="Next page" disabled={page >= pageCount - 1}
                    onClick={() => { setPageRun(result?.run_id); setPage((p) => Math.min(pageCount - 1, p + 1)); }}
                    className="rounded-lg border border-line px-2 py-1 disabled:opacity-40">Next</button>
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {visible.map(([skuId, rows]) => {
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

          {omitted.length > 0 && (
            <div className="rounded-2xl border border-line bg-surface p-4">
              <p className="text-sm font-semibold text-content">
                {omitted.length} SKU{omitted.length === 1 ? "" : "s"} not forecast
              </p>
              <ul className="mt-2 divide-y divide-line text-xs">
                {omitted.map((o) => (
                  <li key={o.sku_id} className="flex justify-between gap-4 py-1.5">
                    <span className="font-mono">{skuLookup.get(o.sku_id)?.code ?? o.sku_id}</span>
                    <span className="text-content-muted text-right">{omissionReason(o)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* The confidence drill-down follows the forecast itself, so the
              planner sees the answer before the model diagnostics. */}
          <ForecastConfidencePanel />
        </div>
      )}
    </div>
  );
};
