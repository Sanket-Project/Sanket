import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  FileSpreadsheet,
  Sprout,
  Cpu,
  Shirt,
  Pill,
  Wrench,
  TrendingUp,
  Package,
  Clock,
  CheckCircle2,
  ChevronRight,
  Filter,
  LayoutGrid,
  List,
  Trash2,
} from "@/components/ui/icons";
import clsx from "clsx";
import { skusApi } from "@/api/skus";
import { exportApi } from "@/api/export";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ImportModal } from "@/components/ui/ImportModal";
import { fmtNumber, fmtRelative } from "@/utils/format";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { getErrorMessage } from "@/utils/errors";

import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getProductImage, useProductImagesStore } from "@/stores/productImages";
import { industryAccent, industryGradient, industryDisplay } from "@/utils/colors";
import {
  parseFile,
  validateSkuRows,
  downloadSkuTemplate,
  SKU_REQUIRED_COLUMNS,
  SKU_ALL_COLUMNS,
} from "@/utils/csvImport";
import toast from "react-hot-toast";
import type { Sku, IndustryCode } from "@/types/api";

// ─────────────────────────────────────────────────────────────────────────────
// Industry config
// ─────────────────────────────────────────────────────────────────────────────
const INDUSTRY_ICONS: Record<IndustryCode, React.ReactNode> = {
  agrocenter: <Sprout size={16} />,
  electronics: <Cpu size={16} />,
  fashion: <Shirt size={16} />,
  pharma: <Pill size={16} />,
  hardware: <Wrench size={16} />,
};

const INDUSTRY_FIELD_LABELS: Record<IndustryCode, { cost: string; price: string; lead: string; moq: string; safety: string; reorder: string }> = {
  agrocenter: { cost: "Input Cost", price: "Selling Price", lead: "Delivery Lead", moq: "Min. Order Qty", safety: "Safety Buffer", reorder: "Reorder Trigger" },
  electronics: { cost: "Unit Cost", price: "Retail Price", lead: "Component Lead", moq: "Min. Order Qty", safety: "Safety Stock", reorder: "Reorder Point" },
  fashion: { cost: "COGS/Unit", price: "Retail Price", lead: "Production Lead", moq: "Min. Run Qty", safety: "Safety Stock", reorder: "Reorder Point" },
  pharma: { cost: "COGS/Unit", price: "WAC Price", lead: "Manufacturing Lead", moq: "Min. Batch Qty", safety: "Safety Level", reorder: "Reorder Signal" },
  hardware: { cost: "Unit Cost", price: "Trade Price", lead: "Supplier Lead", moq: "Min. Order Qty", safety: "Safety Stock", reorder: "Reorder Point" },
};


// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function marginPct(s: Sku): number | null {
  const price = s.unit_price != null ? Number(s.unit_price) : null;
  const cost = s.unit_cost != null ? Number(s.unit_cost) : null;
  if (price == null || cost == null || price === 0) return null;
  return ((price - cost) / price) * 100;
}

function leadToneClass(days: number | null) {
  if (days == null) return "text-slate-400 dark:text-slate-500";
  if (days > 45) return "text-rose-600 dark:text-rose-400";
  if (days > 25) return "text-amber-600 dark:text-amber-400";
  return "text-emerald-600 dark:text-emerald-400";
}

function stockHealthLabel(s: Sku): { label: string; tone: "good" | "warn" | "low" } {
  // Inventory planning params not configured yet — don't infer a health status.
  if (s.safety_stock == null || s.reorder_point == null) return { label: "—", tone: "warn" };
  if (s.safety_stock >= s.reorder_point * 0.6) return { label: "Healthy", tone: "good" };
  if (s.safety_stock >= s.reorder_point * 0.3) return { label: "Low Buffer", tone: "warn" };
  return { label: "At Risk", tone: "low" };
}

// ─────────────────────────────────────────────────────────────────────────────
// SKU Card (grid view)
// ─────────────────────────────────────────────────────────────────────────────
function SkuCard({
  sku,
  accent,
  fields,
  images,
  isSelected,
  onToggleSelect,
  onClick,
}: {
  sku: Sku;
  accent: string;
  fields: typeof INDUSTRY_FIELD_LABELS["fashion"];
  images: Record<string, string>;
  isSelected: boolean;
  onToggleSelect: (e: React.MouseEvent) => void;
  onClick: () => void;
}) {
  const { formatPrice } = useFormattedCurrency();
  const margin = marginPct(sku);
  const health = stockHealthLabel(sku);
  const healthCls = health.tone === "good" ? "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800/40"
    : health.tone === "warn" ? "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/40"
    : "text-rose-500 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800/40";
  const imgUrl = getProductImage(sku.id, sku.industry, images, `${sku.sku_code} ${sku.description ?? ""}`);

  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full overflow-hidden rounded-2xl border text-left shadow-sm transition hover:-translate-y-0.5 hover:border-line-strong hover:shadow-md group cursor-pointer relative",
        isSelected ? "border-violet-500 bg-violet-50/10 ring-2 ring-violet-500/20" : "border-line bg-surface"
      )}
    >
      <div className="relative h-36 overflow-hidden bg-surface-2">
        <img src={imgUrl} alt={sku.description ?? sku.sku_code} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.025]" />
        {/* Selection Checkbox */}
        <div
          className="absolute top-2.5 right-2.5 z-10 bg-white/90 dark:bg-slate-900/90 backdrop-blur-sm p-1 rounded-md shadow"
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect(e);
          }}
        >
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => {}}
            className="h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500 cursor-pointer block"
            aria-label={`Select ${sku.sku_code}`}
          />
        </div>
      </div>

      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <span className="font-mono text-[10px] font-bold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40 block w-fit mb-1.5">
              {sku.sku_code}
            </span>
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug line-clamp-2">{sku.description ?? "—"}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            {sku.is_active ? (
              <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40 px-2 py-0.5 rounded-full">
                <span className="h-1 w-1 rounded-full bg-emerald-500 animate-pulse" />Active
              </span>
            ) : (
              <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/40 px-2 py-0.5 rounded-full">
                Inactive
              </span>
            )}
          </div>
        </div>

        {/* Price row */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-xl font-black text-slate-900 dark:text-white tabular-nums">
              {sku.unit_price != null ? formatPrice(Number(sku.unit_price), sku.currency) : "—"}
            </div>
            <div className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">{fields.price}</div>
          </div>
          {margin !== null && (
            <div className={clsx("text-right")}>
              <div className={clsx("text-lg font-black tabular-nums", margin >= 40 ? "text-emerald-600 dark:text-emerald-400" : margin >= 20 ? "text-amber-600 dark:text-amber-400" : "text-rose-500 dark:text-rose-400")}>
                {margin.toFixed(1)}%
              </div>
              <div className="text-[10px] text-slate-400 dark:text-slate-500">margin</div>
            </div>
          )}
        </div>

        {/* Metrics strip */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          <div className="text-center bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
            <div className={clsx("text-sm font-bold", leadToneClass(sku.lead_time_days))}>
              {sku.lead_time_days != null ? `${sku.lead_time_days}d` : "—"}
            </div>
            <div className="text-[9px] text-slate-400 dark:text-slate-500 mt-0.5">lead time</div>
          </div>
          <div className="text-center bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
            <div className="text-sm font-bold text-slate-700 dark:text-slate-200">
              {fmtNumber(sku.moq)}
            </div>
            <div className="text-[9px] text-slate-400 dark:text-slate-500 mt-0.5">{fields.moq}</div>
          </div>
          <div className="text-center bg-slate-50 dark:bg-slate-800/40 rounded-lg p-2">
            <div className="text-sm font-bold text-slate-700 dark:text-slate-200">
              {fmtNumber(sku.safety_stock)}
            </div>
            <div className="text-[9px] text-slate-400 dark:text-slate-500 mt-0.5">safety</div>
          </div>
        </div>

        {/* Stock health + updated */}
        <div className="flex items-center justify-between">
          <span className={clsx("text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border", healthCls)}>
            {health.label}
          </span>
          <span className="text-[10px] text-slate-400 dark:text-slate-500">{fmtRelative(sku.updated_at)}</span>
        </div>
      </div>

      {/* Hover arrow */}
      <div className="px-5 pb-4 flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity duration-200 -mt-2">
        <span className="flex items-center gap-1 text-[10px] font-bold" style={{ color: accent }}>
          View details <ChevronRight size={11} />
        </span>
      </div>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SKU Row (list view)
// ─────────────────────────────────────────────────────────────────────────────
function SkuRow({
  sku,
  gradient,
  fields,
  isSelected,
  onToggleSelect,
  onClick,
}: {
  sku: Sku;
  gradient: string;
  fields: typeof INDUSTRY_FIELD_LABELS["fashion"];
  isSelected: boolean;
  onToggleSelect: (e: React.MouseEvent) => void;
  onClick: () => void;
}) {
  const { formatPrice } = useFormattedCurrency();
  const margin = marginPct(sku);
  const health = stockHealthLabel(sku);
  const healthCls = health.tone === "good" ? "text-emerald-600 dark:text-emerald-400"
    : health.tone === "warn" ? "text-amber-500 dark:text-amber-400"
    : "text-rose-500 dark:text-rose-400";

  return (
    <button
      onClick={onClick}
      className={clsx(
        "w-full text-left flex items-center gap-4 p-3.5 rounded-xl transition-colors group border cursor-pointer",
        isSelected
          ? "bg-violet-50/20 border-violet-300 dark:border-violet-700/50"
          : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/40 hover:border-slate-200/60 dark:hover:border-slate-700/40"
      )}
    >
      {/* Checkbox */}
      <div
        className="shrink-0 p-1"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect(e);
        }}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => {}}
          className="h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500 cursor-pointer block"
          aria-label={`Select ${sku.sku_code}`}
        />
      </div>

      {/* Colour dot */}
      <div className="h-8 w-1.5 rounded-full shrink-0" style={{ background: gradient }} />

      {/* SKU code + name */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-mono text-[10px] font-bold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40">
            {sku.sku_code}
          </span>
          {sku.is_active ? (
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" title="Active" />
          ) : (
            <span className="h-1.5 w-1.5 rounded-full bg-slate-300 dark:bg-slate-600" title="Inactive" />
          )}
        </div>
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 truncate">{sku.description ?? sku.sku_code}</p>
      </div>

      {/* Price */}
      <div className="text-right shrink-0 w-20 hidden sm:block">
        <div className="text-sm font-bold text-slate-800 dark:text-slate-100">{sku.unit_price != null ? formatPrice(Number(sku.unit_price), sku.currency) : "—"}</div>
        <div className="text-[10px] text-slate-400 dark:text-slate-500">{fields.price}</div>
      </div>

      {/* Margin */}
      <div className="text-right shrink-0 w-16 hidden md:block">
        {margin !== null && (
          <>
            <div className={clsx("text-sm font-bold", margin >= 40 ? "text-emerald-600 dark:text-emerald-400" : margin >= 20 ? "text-amber-600 dark:text-amber-400" : "text-rose-500")}>{margin.toFixed(1)}%</div>
            <div className="text-[10px] text-slate-400 dark:text-slate-500">margin</div>
          </>
        )}
      </div>

      {/* Lead time */}
      <div className="text-right shrink-0 w-16 hidden lg:block">
        <div className={clsx("text-sm font-bold", leadToneClass(sku.lead_time_days))}>
          {sku.lead_time_days != null ? `${sku.lead_time_days}d` : "—"}
        </div>
        <div className="text-[10px] text-slate-400 dark:text-slate-500">lead time</div>
      </div>

      {/* Safety stock */}
      <div className="text-right shrink-0 w-20 hidden lg:block">
        <div className="text-sm font-bold text-slate-700 dark:text-slate-200">{fmtNumber(sku.safety_stock)}</div>
        <div className="text-[10px] text-slate-400 dark:text-slate-500">safety stock</div>
      </div>

      {/* Health */}
      <div className={clsx("text-[10px] font-bold w-20 text-right shrink-0 hidden xl:block", healthCls)}>
        {health.label}
      </div>

      {/* Updated */}
      <div className="text-[10px] text-slate-400 dark:text-slate-500 shrink-0 w-24 text-right hidden xl:block">
        {fmtRelative(sku.updated_at)}
      </div>

      <ChevronRight size={14} className="text-slate-300 dark:text-slate-600 group-hover:text-slate-500 dark:group-hover:text-slate-400 transition-colors shrink-0" />
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
type ViewMode = "grid" | "list";
type FilterStatus = "all" | "active" | "inactive";
type SortKey = "sku_code" | "unit_price" | "margin" | "lead_time_days" | "updated_at";

export const SkusPage = () => {
  const navigate = useNavigate();
  const industry = useWorkspaceIndustry();
  const images = useProductImagesStore((s) => s.images);
  const accent = industryAccent[industry];
  const gradient = industryGradient[industry];
  const displayName = industryDisplay[industry];
  const icon = INDUSTRY_ICONS[industry];
  const fields = INDUSTRY_FIELD_LABELS[industry];

  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [sortKey, setSortKey] = useState<SortKey>("updated_at");
  const [importOpen, setImportOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const [confirmDeleteSelected, setConfirmDeleteSelected] = useState(false);
  const qc = useQueryClient();

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const { data: liveSkus } = useQuery({
    queryKey: ["skus", "list"],
    queryFn: () => skusApi.list({ limit: 200, active_only: false }),
    retry: 1,
  });

  const skus: Sku[] = useMemo(() => liveSkus || [], [liveSkus]);

  const deleteAllMutation = useMutation({
    mutationFn: () => skusApi.deleteAll(),
    onSuccess: (res) => {
      toast.success(`Deleted all ${res.deleted} SKUs`);
      setSelectedIds(new Set());
      setConfirmDeleteAll(false);
      qc.invalidateQueries({ queryKey: ["skus"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Failed to delete all SKUs"));
      setConfirmDeleteAll(false);
    },
  });

  const deleteSelectedMutation = useMutation({
    mutationFn: () => skusApi.deleteMany(Array.from(selectedIds)),
    onSuccess: (res) => {
      toast.success(`Deleted ${res.deleted} SKU${res.deleted !== 1 ? "s" : ""}`);
      setSelectedIds(new Set());
      setConfirmDeleteSelected(false);
      qc.invalidateQueries({ queryKey: ["skus"] });
      qc.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Failed to delete selected SKUs"));
      setConfirmDeleteSelected(false);
    },
  });

  const filtered = useMemo(() => {
    let list = skus;
    if (filterStatus === "active") list = list.filter((s) => s.is_active);
    if (filterStatus === "inactive") list = list.filter((s) => !s.is_active);
    if (query) {
      const q = query.toLowerCase();
      list = list.filter((s) =>
        s.sku_code.toLowerCase().includes(q) ||
        (s.description ?? "").toLowerCase().includes(q) ||
        (s.external_id ?? "").toLowerCase().includes(q)
      );
    }
    return [...list].sort((a, b) => {
      switch (sortKey) {
        case "sku_code": return a.sku_code.localeCompare(b.sku_code);
        case "unit_price": return (b.unit_price ?? 0) - (a.unit_price ?? 0);
        case "margin": return (marginPct(b) ?? 0) - (marginPct(a) ?? 0);
        case "lead_time_days": return (a.lead_time_days ?? 999) - (b.lead_time_days ?? 999);
        case "updated_at": return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        default: return 0;
      }
    });
  }, [skus, query, filterStatus, sortKey]);

  const activeCount = skus.filter((s) => s.is_active).length;
  const highLeadCount = skus.filter((s) => (s.lead_time_days ?? 0) > 45).length;
  const avgMargin = skus.reduce((sum, s) => sum + (marginPct(s) ?? 0), 0) / (skus.length || 1);

  return (
    <div className="space-y-4 animate-fade-in" data-industry={industry}>

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold text-white mb-3"
            style={{ background: gradient }}
          >
            {icon} {displayName}
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            SKU Catalogue
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-xl leading-relaxed">
            All stock-keeping units for this industry. Each SKU carries cost, pricing, lead time, and safety stock values that flow directly into demand forecasts and replenishment logic.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            icon={<FileSpreadsheet size={14} />}
            onClick={() => exportApi.skusCsv().catch(() => toast.error("Export failed"))}
            className="glass border border-slate-200 dark:border-slate-700"
          >
            Export CSV
          </Button>
          <Button
            variant="secondary"
            icon={<FileSpreadsheet size={14} />}
            onClick={() => setImportOpen(true)}
            className="glass border border-slate-200 dark:border-slate-700"
          >
            Import CSV
          </Button>
          <Button
            variant="secondary"
            icon={<Trash2 size={14} />}
            onClick={() => setConfirmDeleteAll(true)}
            disabled={skus.length === 0}
            className="text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/20 border border-rose-200 dark:border-rose-900/40"
          >
            Delete All
          </Button>
        </div>
      </div>

      {/* ── Summary KPIs ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Total SKUs", value: skus.length.toString(), sub: `${activeCount} active`, icon: <Package size={15} />, tone: "default" },
          { label: "Active SKUs", value: activeCount.toString(), sub: `${skus.length - activeCount} inactive`, icon: <CheckCircle2 size={15} />, tone: "up" },
          { label: "Long Lead SKUs", value: highLeadCount.toString(), sub: ">45 day lead time", icon: <Clock size={15} />, tone: highLeadCount > 0 ? "warn" : "up" },
          { label: "Avg. Margin", value: `${avgMargin.toFixed(1)}%`, sub: "across all SKUs", icon: <TrendingUp size={15} />, tone: avgMargin >= 40 ? "up" : avgMargin >= 20 ? "warn" : "down" },
        ].map(({ label, value, sub, icon: ic, tone }) => (
          <div key={label} className="glass rounded-2xl p-4">
            <div className={clsx(
              "h-8 w-8 rounded-lg flex items-center justify-center mb-3",
              tone === "up" ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400" :
              tone === "warn" ? "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400" :
              tone === "down" ? "bg-rose-50 dark:bg-rose-900/20 text-rose-500 dark:text-rose-400" :
              "bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400"
            )}>
              {ic}
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white">{value}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mt-0.5">{label}</div>
            <div className="text-[10px] text-slate-400 dark:text-slate-500">{sub}</div>
          </div>
        ))}
      </div>

      {/* ── Controls bar ── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="flex-1 min-w-48 max-w-72">
          <Input
            icon={<Search size={14} />}
            placeholder="Search code, name, external ID…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {/* Status filter */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/60 rounded-xl p-1">
          {(["all", "active", "inactive"] as FilterStatus[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilterStatus(f)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-[11px] font-bold capitalize transition-all",
                filterStatus === f
                  ? "bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm"
                  : "text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300"
              )}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Sort */}
        <div className="flex items-center gap-2">
          <Filter size={13} className="text-slate-400 dark:text-slate-500" />
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            title="Sort SKUs"
            aria-label="Sort SKUs"
            className="text-xs font-semibold text-slate-600 dark:text-slate-300 bg-transparent border-none outline-none cursor-pointer"
          >
            <option value="updated_at">Recently updated</option>
            <option value="sku_code">SKU code</option>
            <option value="unit_price">Price ↓</option>
            <option value="margin">Margin ↓</option>
            <option value="lead_time_days">Lead time ↑</option>
          </select>
        </div>

        {/* View toggle */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/60 rounded-xl p-1 ml-auto">
          <button
            onClick={() => setViewMode("grid")}
            title="Grid view"
            aria-label="Grid view"
            className={clsx("p-1.5 rounded-lg transition", viewMode === "grid" ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100" : "text-slate-400 dark:text-slate-500")}
          >
            <LayoutGrid size={14} />
          </button>
          <button
            onClick={() => setViewMode("list")}
            title="List view"
            aria-label="List view"
            className={clsx("p-1.5 rounded-lg transition", viewMode === "list" ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100" : "text-slate-400 dark:text-slate-500")}
          >
            <List size={14} />
          </button>
        </div>
      </div>

      {/* ── Bulk selection bar ── */}
      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-2xl bg-violet-500/10 border border-violet-500/30 backdrop-blur-md animate-fade-in">
          <div className="flex items-center gap-2 text-xs font-bold text-violet-700 dark:text-violet-300">
            <span className="h-2 w-2 rounded-full bg-violet-500 animate-pulse" />
            <span>
              {selectedIds.size} of {skus.length} SKU{selectedIds.size !== 1 ? "s" : ""} selected
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setSelectedIds(new Set())}
              className="text-xs"
            >
              Deselect All
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setSelectedIds(new Set(filtered.map((s) => s.id)))}
              className="text-xs"
            >
              Select Filtered ({filtered.length})
            </Button>
            <Button
              size="sm"
              icon={<Trash2 size={13} />}
              onClick={() => setConfirmDeleteSelected(true)}
              className="bg-rose-600 hover:bg-rose-700 text-white text-xs"
            >
              Delete Selected ({selectedIds.size})
            </Button>
          </div>
        </div>
      )}

      {/* ── SKU Grid / List ── */}
      {skus.length === 0 ? (
        <div className="glass rounded-2xl p-16 text-center">
          <Package size={32} className="mx-auto text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">Your SKU Catalogue is Empty</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Import SKUs via CSV to get started.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass rounded-2xl p-16 text-center">
          <Package size={32} className="mx-auto text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No SKUs match your search</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Try adjusting your filter or search term</p>
        </div>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((sku) => (
            <SkuCard
              key={sku.id}
              sku={sku}
              accent={accent}
              fields={fields}
              images={images}
              isSelected={selectedIds.has(sku.id)}
              onToggleSelect={() => toggleSelect(sku.id)}
              onClick={() => navigate(`/workspace/skus/${sku.id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="glass rounded-2xl overflow-hidden">
          {/* List header */}
          <div className="flex items-center gap-4 px-4 py-2.5 border-b border-slate-100 dark:border-slate-700/40 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            <div className="shrink-0 p-1">
              <input
                type="checkbox"
                checked={filtered.length > 0 && filtered.every((s) => selectedIds.has(s.id))}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedIds((prev) => {
                      const next = new Set(prev);
                      filtered.forEach((s) => next.add(s.id));
                      return next;
                    });
                  } else {
                    setSelectedIds((prev) => {
                      const next = new Set(prev);
                      filtered.forEach((s) => next.delete(s.id));
                      return next;
                    });
                  }
                }}
                className="h-4 w-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500 cursor-pointer block"
                aria-label="Select all SKUs"
              />
            </div>
            <div className="w-1.5 shrink-0" />
            <div className="flex-1">SKU</div>
            <div className="w-20 text-right hidden sm:block">{fields.price}</div>
            <div className="w-16 text-right hidden md:block">Margin</div>
            <div className="w-16 text-right hidden lg:block">Lead Time</div>
            <div className="w-20 text-right hidden lg:block">Safety Stock</div>
            <div className="w-20 text-right hidden xl:block">Health</div>
            <div className="w-24 text-right hidden xl:block">Updated</div>
            <div className="w-4 shrink-0" />
          </div>
          <div className="divide-y divide-slate-100/60 dark:divide-slate-700/30 p-2">
            {filtered.map((sku) => (
              <SkuRow
                key={sku.id}
                sku={sku}
                gradient={gradient}
                fields={fields}
                isSelected={selectedIds.has(sku.id)}
                onToggleSelect={() => toggleSelect(sku.id)}
                onClick={() => navigate(`/workspace/skus/${sku.id}`)}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Result count ── */}
      <p className="text-[11px] text-slate-400 dark:text-slate-500 text-center">
        Showing <strong className="text-slate-600 dark:text-slate-300">{filtered.length}</strong> of <strong className="text-slate-600 dark:text-slate-300">{skus.length}</strong> SKUs
      </p>

      {/* ── Import Modal ── */}
      <ImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import SKUs"
        description="Upload a CSV or Excel file to bulk-add SKUs and link them to existing products"
        requiredColumns={SKU_REQUIRED_COLUMNS}
        optionalColumns={SKU_ALL_COLUMNS.filter(
          (c) => !SKU_REQUIRED_COLUMNS.includes(c as (typeof SKU_REQUIRED_COLUMNS)[number]),
        )}
        tip='"product_external_id" must match the external_id of an existing product. Import products first if needed.'
        onDownloadTemplate={downloadSkuTemplate}
        onParse={async (file) => {
          const parsed = await parseFile(file);
          const validation = validateSkuRows(parsed.rows);
          return { parsed, validation };
        }}
        onImport={async (rows, onProgress) => {
          const result = await skusApi.bulkCreate(rows, onProgress);
          qc.invalidateQueries({ queryKey: ["skus"] });
          if (result.created > 0) {
            toast.success(`${result.created} SKU${result.created !== 1 ? "s" : ""} imported`);
          }
          return result;
        }}
      />

      {/* ── Confirm Delete All Dialog ── */}
      <ConfirmDialog
        open={confirmDeleteAll}
        onClose={() => setConfirmDeleteAll(false)}
        title="Delete All SKUs"
        tone="danger"
        loading={deleteAllMutation.isPending}
        confirmLabel="Delete All SKUs"
        message={
          <div className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
            <p>
              Are you sure you want to delete all <strong>{skus.length}</strong> SKUs in the{" "}
              <strong>{displayName}</strong> catalogue?
            </p>
            <p className="text-xs text-rose-600 dark:text-rose-400 font-medium">
              This action permanently deletes all SKU records and stock positions in this industry. It cannot be undone.
            </p>
          </div>
        }
        onConfirm={() => deleteAllMutation.mutate()}
      />

      {/* ── Confirm Delete Selected Dialog ── */}
      <ConfirmDialog
        open={confirmDeleteSelected}
        onClose={() => setConfirmDeleteSelected(false)}
        title="Delete Selected SKUs"
        tone="danger"
        loading={deleteSelectedMutation.isPending}
        confirmLabel={`Delete ${selectedIds.size} SKU${selectedIds.size !== 1 ? "s" : ""}`}
        message={
          <div className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
            <p>
              Are you sure you want to delete the <strong>{selectedIds.size}</strong> selected SKUs?
            </p>
            <p className="text-xs text-rose-600 dark:text-rose-400 font-medium">
              This action cannot be undone.
            </p>
          </div>
        }
        onConfirm={() => deleteSelectedMutation.mutate()}
      />
    </div>
  );
};
