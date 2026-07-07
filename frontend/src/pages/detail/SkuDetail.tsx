import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Play,
  Camera,
  Trash2,
  Package,
  Clock,
  ShieldCheck,
  DollarSign,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Tag,
  Layers,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
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
import { skusApi } from "@/api/skus";
import { forecastsApi } from "@/api/forecasts";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageLoader } from "@/components/ui/Spinner";
import { useIndustryStore } from "@/stores/industry";
import { industryAccent, industryGradient, industryDisplay } from "@/utils/colors";
import { fmtDate, fmtNumber, fmtCompact } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import type { ForecastRow, IndustryCode } from "@/types/api";
import { useProductImagesStore, getProductImage } from "@/stores/productImages";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";

// ─────────────────────────────────────────────────────────────────────────────
// Horizon presets (reuse from Forecasts page pattern)
// ─────────────────────────────────────────────────────────────────────────────
const HORIZON_PRESETS: Record<IndustryCode, { label: string; weeks: number; recommended?: boolean }[]> = {
  agrocenter: [{ label: "8w", weeks: 8 }, { label: "26w", weeks: 26, recommended: true }, { label: "52w", weeks: 52 }],
  electronics: [{ label: "8w", weeks: 8 }, { label: "12w", weeks: 12, recommended: true }, { label: "26w", weeks: 26 }],
  fashion: [{ label: "4w", weeks: 4 }, { label: "8w", weeks: 8 }, { label: "12w", weeks: 12, recommended: true }],
  pharma: [{ label: "13w", weeks: 13 }, { label: "26w", weeks: 26 }, { label: "52w", weeks: 52, recommended: true }],
  hardware: [{ label: "8w", weeks: 8 }, { label: "16w", weeks: 16, recommended: true }, { label: "26w", weeks: 26 }],
};



// ─────────────────────────────────────────────────────────────────────────────
// Metric tile
// ─────────────────────────────────────────────────────────────────────────────
function MetricTile({ label, value, sub, icon, tone = "default" }: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  icon: React.ReactNode;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const iconCls = {
    default: "bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400",
    good: "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400",
    warn: "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400",
    bad: "bg-rose-50 dark:bg-rose-900/20 text-rose-500 dark:text-rose-400",
  }[tone];

  return (
    <div className="glass rounded-xl p-4">
      <div className={clsx("h-8 w-8 rounded-lg flex items-center justify-center mb-2.5", iconCls)}>
        {icon}
      </div>
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{label}</div>
      <div className="text-xl font-black text-slate-900 dark:text-white">{value}</div>
      {sub && <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Forecast chart (P10/P50/P90 band)
// ─────────────────────────────────────────────────────────────────────────────
function SkuForecastChart({ rows, accent, skuCode }: { rows: ForecastRow[]; accent: string; skuCode: string }) {
  const [expanded, setExpanded] = useState(false);

  const chartData = rows.map((r) => ({
    date: r.forecast_date,
    p10: r.p10,
    p50: r.p50,
    p90: r.p90,
  }));

  const p50s = rows.map((r) => r.p50);
  const trend = p50s[p50s.length - 1] - p50s[0];
  const trendPct = ((trend / (p50s[0] || 1)) * 100).toFixed(1);
  const isUp = trend > 0;

  return (
    <div>
      {/* Chart header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className={clsx("flex items-center gap-1.5 text-sm font-bold", isUp ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400")}>
            {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
            {isUp ? "+" : ""}{trendPct}% over horizon
          </div>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">
            Peak P50: <strong className="text-slate-700 dark:text-slate-200">{fmtCompact(Math.max(...p50s))}</strong> · Floor: <strong className="text-slate-700 dark:text-slate-200">{fmtCompact(Math.min(...p50s))}</strong>
          </p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="h-7 w-7 rounded-lg bg-slate-100 dark:bg-slate-800/60 flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      <ResponsiveContainer width="100%" height={expanded ? 320 : 220}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id={`fg-${skuCode}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity={0.28} />
              <stop offset="100%" stopColor={accent} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 6" stroke="#e2e8f0" className="dark:stroke-slate-700/40" />
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
          />
          <Tooltip
            contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, fontSize: 11, boxShadow: "0 4px 20px rgba(15,23,42,0.08)" }}
            labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
            formatter={(value: number, name: string) => {
              const labels: Record<string, string> = { p10: "P10 Conservative", p50: "P50 Expected", p90: "P90 Optimistic" };
              return [fmtNumber(value), labels[name] ?? name];
            }}
          />
          <ReferenceLine x={new Date().toISOString().slice(0, 10)} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: "Today", position: "top", fontSize: 9, fill: "#94a3b8" }} />
          <Area type="monotone" dataKey="p90" stroke="none" fill={`url(#fg-${skuCode})`} isAnimationActive />
          <Line type="monotone" dataKey="p10" stroke="#ef4444" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive animationDuration={1200} />
          <Line type="monotone" dataKey="p90" stroke="#10b981" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive animationDuration={1200} />
          <Line type="monotone" dataKey="p50" stroke={accent} strokeWidth={2.5} dot={false} isAnimationActive animationDuration={1500} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 flex-wrap">
        {[{ color: accent, label: "P50 Expected" }, { color: "#10b981", label: "P90 Optimistic", dash: true }, { color: "#ef4444", label: "P10 Conservative", dash: true }].map(({ color, label, dash }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="h-px w-5" style={{ background: color, borderTop: dash ? `1.5px dashed ${color}` : `2.5px solid ${color}` }} />
            <span className="text-[9px] font-semibold text-slate-500 dark:text-slate-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
export const SkuDetailPage = () => {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { formatPrice, activeCurrency } = useFormattedCurrency();
  const qc = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const industry = useIndustryStore((s) => s.activeIndustry);
  const accent = industryAccent[industry];
  const gradient = industryGradient[industry];
  const displayName = industryDisplay[industry];
  const presets = HORIZON_PRESETS[industry];
  const defaultHorizon = presets.find((p) => p.recommended)?.weeks ?? 12;

  const [horizon, setHorizon] = useState(defaultHorizon);
  const [forecastRows, setForecastRows] = useState<ForecastRow[] | null>(null);

  const { data: sku, isLoading } = useQuery({
    queryKey: ["sku", id],
    queryFn: () => skusApi.get(id),
    enabled: !!id,
  });

  const toggle = useMutation({
    mutationFn: (active: boolean) => skusApi.update(id, { is_active: active }),
    onSuccess: () => {
      toast.success("SKU updated");
      qc.invalidateQueries({ queryKey: ["sku", id] });
      qc.invalidateQueries({ queryKey: ["skus"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => skusApi.remove(id),
    onSuccess: () => {
      toast.success("SKU deleted");
      qc.invalidateQueries({ queryKey: ["skus"] });
      navigate("/workspace/skus");
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Could not delete this SKU"));
      setConfirmDelete(false);
    },
  });

  const runForecast = useMutation({
    mutationFn: () => forecastsApi.generate({ horizon }),
    onSuccess: (r) => {
      const rows = r.rows.filter((row) => row.sku_id === id || (sku && row.sku_id === sku.sku_code));
      if (rows.length > 0) {
        setForecastRows(rows);
        toast.success(`${rows.length} forecast points generated`);
      } else {
        setForecastRows([]);
        toast.error("No forecast data generated for this SKU.");
      }
    },
    onError: () => {
      setForecastRows([]);
      toast.error("Failed to generate forecast.");
    },
  });

  // Auto-generate forecast on mount and when SKU or horizon changes
  useEffect(() => {
    if (sku) {
      runForecast.mutate();
    }
  }, [sku, horizon]);

  const { images, uploadImage, removeImage } = useProductImagesStore();

  if (isLoading || !sku) return <PageLoader />;

  const imgUrl = getProductImage(sku.id, sku.industry, images);
  const price = sku.unit_price != null ? Number(sku.unit_price) : null;
  const cost = sku.unit_cost != null ? Number(sku.unit_cost) : null;
  const margin = price && cost && price > 0
    ? ((price - cost) / price) * 100
    : null;
  const leadTone = (sku.lead_time_days ?? 0) > 45 ? "bad" : (sku.lead_time_days ?? 0) > 25 ? "warn" : "good";

  return (
    <div className="space-y-6 animate-fade-in">

      {/* ── Breadcrumb + actions ── */}
      <div className="flex items-center justify-between">
        <Link
          to="/workspace/skus"
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
        >
          <ArrowLeft size={14} /> Back to SKUs
        </Link>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full border" style={{ background: `${accent}15`, borderColor: `${accent}40`, color: accent }}>
            {displayName}
          </span>
          <Button
            variant={sku.is_active ? "secondary" : "primary"}
            size="sm"
            loading={toggle.isPending}
            onClick={() => toggle.mutate(!sku.is_active)}
            className={clsx("font-semibold", sku.is_active ? "border border-slate-200 dark:border-slate-700" : "")}
          >
            {sku.is_active ? "Deactivate" : "Activate"}
          </Button>
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 size={13} />}
            onClick={() => setConfirmDelete(true)}
            className="font-semibold"
          >
            Delete
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this SKU?"
        confirmLabel="Delete SKU"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onClose={() => setConfirmDelete(false)}
        message={
          <>
            <p>
              Permanently delete <strong className="font-mono">{sku.sku_code}</strong>? This
              removes it from the catalogue and forecasting. Historical sales records are kept.
            </p>
            <p className="mt-2 text-xs text-slate-400">This action cannot be undone.</p>
          </>
        }
      />

      {/* ── Hero card ── */}
      <div className="glass rounded-2xl overflow-hidden">
        {/* Top gradient bar */}
        <div className="h-1.5 w-full" style={{ background: gradient }} />

        <div className="p-6">
          <div className="flex flex-col md:flex-row gap-6 items-start">
            {/* Product image */}
            <div className="relative h-36 w-36 rounded-2xl overflow-hidden bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/40 shadow-md group shrink-0">
              <img src={imgUrl} alt={sku.sku_code} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
              <label className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer select-none text-center p-2">
                <Camera size={18} className="mb-1 text-violet-300" />
                <span className="text-[10px] font-bold tracking-wide uppercase">Change Photo</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onloadend = () => { uploadImage(sku.id, reader.result as string); toast.success("Image updated!"); };
                      reader.readAsDataURL(file);
                    }
                  }}
                  className="hidden"
                />
              </label>
              {images[sku.id] && (
                <button
                  type="button"
                  onClick={() => { removeImage(sku.id); toast.success("Image removed"); }}
                  className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 hover:bg-rose-600/90 text-white transition border-none cursor-pointer flex items-center justify-center"
                >
                  <Trash2 size={11} />
                </button>
              )}
            </div>

            {/* Identity info */}
            <div className="flex-1 min-w-0">
              {/* Badges */}
              <div className="flex flex-wrap items-center gap-2 mb-3">
                {sku.is_active ? (
                  <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40 px-2.5 py-1 rounded-full">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> Active
                  </span>
                ) : (
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 px-2.5 py-1 rounded-full">
                    Inactive
                  </span>
                )}
                {sku.gtin && (
                  <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">
                    GTIN {sku.gtin}
                  </span>
                )}
                {sku.external_id && (
                  <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">
                    ext: {sku.external_id}
                  </span>
                )}
              </div>

              <h1 className="font-mono text-xl font-black text-slate-900 dark:text-white tracking-tight mb-1">{sku.sku_code}</h1>
              <p className="text-sm font-medium text-slate-600 dark:text-slate-300 mb-4">{sku.description ?? "No description"}</p>

              {/* Dates */}
              <div className="flex flex-wrap gap-4 text-[11px] text-slate-400 dark:text-slate-500">
                <span>Created <strong className="text-slate-600 dark:text-slate-300">{fmtDate(sku.created_at)}</strong></span>
                <span>Updated <strong className="text-slate-600 dark:text-slate-300">{fmtDate(sku.updated_at)}</strong></span>
                <span className="font-mono text-[10px] bg-slate-100 dark:bg-slate-800/60 px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40 text-slate-500 dark:text-slate-400">{sku.id.slice(0, 18)}…</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Key Metrics grid ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricTile
          label="Unit Cost"
          value={formatPrice(sku.unit_cost, sku.currency)}
          sub={`Currency: ${activeCurrency}`}
          icon={<DollarSign size={15} />}
        />
        <MetricTile
          label="Selling Price"
          value={formatPrice(sku.unit_price, sku.currency)}
          sub={margin != null ? `${margin.toFixed(1)}% margin` : undefined}
          icon={<Tag size={15} />}
          tone={margin != null ? (margin >= 40 ? "good" : margin >= 20 ? "warn" : "bad") : "default"}
        />
        <MetricTile
          label="Lead Time"
          value={sku.lead_time_days != null ? `${sku.lead_time_days}d` : "—"}
          sub={leadTone === "bad" ? "⚠ Long lead time" : leadTone === "warn" ? "Moderate lead time" : "Short lead time"}
          icon={<Clock size={15} />}
          tone={leadTone}
        />
        <MetricTile
          label="Min. Order Qty"
          value={fmtNumber(sku.moq)}
          sub="Per purchase order"
          icon={<Layers size={15} />}
        />
        <MetricTile
          label="Safety Stock"
          value={fmtNumber(sku.safety_stock)}
          sub="Minimum buffer level"
          icon={<ShieldCheck size={15} />}
          tone="good"
        />
        <MetricTile
          label="Reorder Point"
          value={fmtNumber(sku.reorder_point)}
          sub="Trigger replenishment"
          icon={<RefreshCw size={15} />}
          tone="warn"
        />
        <MetricTile
          label="Gross Margin"
          value={margin != null ? `${margin.toFixed(1)}%` : "—"}
          sub="(Price − Cost) / Price"
          icon={<TrendingUp size={15} />}
          tone={margin != null ? (margin >= 40 ? "good" : margin >= 20 ? "warn" : "bad") : "default"}
        />
        <MetricTile
          label="Industry"
          value={<span className="capitalize">{sku.industry}</span>}
          sub={displayName}
          icon={<Package size={15} />}
        />
      </div>

      {/* ── Forecast section ── */}
      <div className="glass rounded-2xl overflow-hidden">
        <div className="h-1 w-full" style={{ background: gradient }} />
        <div className="p-6">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Demand Forecast for this SKU</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Probabilistic projection using the active industry ensemble. Shows P10 (conservative), P50 (expected), and P90 (optimistic).
              </p>
            </div>

          </div>

          {/* Horizon selector */}
          <div className="mb-5">
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2">
              Forecast horizon
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {presets.map(({ label, weeks, recommended }) => (
                <button
                  key={weeks}
                  onClick={() => setHorizon(weeks)}
                  className={clsx(
                    "relative px-4 py-1.5 rounded-xl text-xs font-bold border transition-all",
                    horizon === weeks
                      ? "text-white border-transparent shadow-sm"
                      : "bg-white dark:bg-slate-800/60 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-slate-300"
                  )}
                  style={horizon === weeks ? { background: gradient } : {}}
                >
                  {label}
                  {recommended && (
                    <span className="absolute -top-1.5 -right-1.5 text-[7px] font-black bg-amber-400 text-white px-1 py-0.5 rounded-full leading-none">REC</span>
                  )}
                </button>
              ))}
              <Button
                icon={runForecast.isPending ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
                loading={runForecast.isPending}
                onClick={() => runForecast.mutate()}
                size="sm"
                className="btn-primary font-semibold ml-1"
              >
                {runForecast.isPending ? "Generating…" : "Run Forecast"}
              </Button>
            </div>
          </div>

          {/* Chart or empty state */}
          {forecastRows && forecastRows.length > 0 ? (
            <SkuForecastChart rows={forecastRows} accent={accent} skuCode={sku.sku_code} />
          ) : (
            <div className="py-16 text-center">
              <div className="h-14 w-14 rounded-2xl mx-auto mb-4 flex items-center justify-center" style={{ background: `${accent}15` }}>
                <TrendingUp size={22} style={{ color: accent }} />
              </div>
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-1">No forecast yet</p>
              <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xs mx-auto">
                Select a horizon and press <strong className="text-slate-600 dark:text-slate-300">Run Forecast</strong> to generate probabilistic demand projections for this SKU.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ── Attributes ── */}
      {Object.keys(sku.attributes).length > 0 && (
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Tag size={14} className="text-slate-400 dark:text-slate-500" />
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">Product Attributes</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(sku.attributes).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-700/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 capitalize">{k.replace(/_/g, " ")}</span>
                <span className="text-xs font-bold text-slate-800 dark:text-slate-100 truncate max-w-[55%] text-right">
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
