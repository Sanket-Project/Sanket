import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Warehouse,
  Upload,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Info,
  TrendingDown,
  Package,
  Search,
  ArrowRight,
} from "@/components/ui/icons";
import clsx from "clsx";

import { inventoryApi, validateInventoryRows, downloadInventoryTemplate } from "@/api/inventory";
import { exportApi } from "@/api/export";
import toast from "react-hot-toast";
import type { InventoryLevel, InventoryUpsertItem } from "@/api/inventory";
import { skusApi } from "@/api/skus";
import { parseFile } from "@/utils/csvImport";
import type { ParsedRow } from "@/utils/csvImport";
import { ImportModal } from "@/components/ui/ImportModal";
import type { ImportResult } from "@/components/ui/ImportModal";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { decisionsApi, type Decision } from "@/api/decisions";
import { getProductImage, useProductImagesStore } from "@/stores/productImages";

// ── Coverage classification ────────────────────────────────────────────────

const INVENTORY_REQUIRED_COLUMNS = ["sku_code", "on_hand_units"] as const;
const INVENTORY_OPTIONAL_COLUMNS = ["inbound_units", "reserved_units", "location"] as const;

type CoverageStatus = "healthy" | "low" | "critical" | "overstock" | "unknown";

function classifyCoverage(level: InventoryLevel): CoverageStatus {
  const avail = level.available_units;
  // Without a demand rate we classify on absolute on-hand alone,
  // using inbound as a buffer signal.
  if (avail === 0 && level.inbound_units === 0) return "critical";
  if (avail === 0) return "low";
  if (avail < 20) return "low"; // arbitrary low-stock threshold for display
  return "healthy";
}

function classifyCoverageWithContext(
  level: InventoryLevel,
  context?: { daysOfCover: number | null; leadTimeDays: number },
): CoverageStatus {
  if (typeof context?.daysOfCover === "number") {
    if (context.daysOfCover <= context.leadTimeDays) return "critical";
    if (context.daysOfCover <= context.leadTimeDays * 1.5) return "low";
  }
  return classifyCoverage(level);
}

const STATUS_CONFIG: Record<CoverageStatus, { label: string; classes: string; dot: string }> = {
  healthy:   { label: "Healthy",    classes: "bg-emerald-50 text-emerald-700 border-emerald-200",  dot: "bg-emerald-400" },
  low:       { label: "Low",        classes: "bg-amber-50 text-amber-700 border-amber-200",        dot: "bg-amber-400"   },
  critical:  { label: "Critical",   classes: "bg-red-50 text-red-700 border-red-200",              dot: "bg-red-500"     },
  overstock: { label: "Overstock",  classes: "bg-blue-50 text-blue-700 border-blue-200",           dot: "bg-blue-400"    },
  unknown:   { label: "No data",    classes: "bg-slate-50 text-slate-500 border-slate-200",        dot: "bg-slate-300"   },
};

const StatusBadge = ({ status }: { status: CoverageStatus }) => {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={clsx("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium", cfg.classes)}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
};

// ── Source badge — tells user if a row is real stock or an estimate ─────────

const SourceBadge = ({ source }: { source: string }) => {
  const isFallback = source === "seed" || source === "fallback";
  if (isFallback) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-700 border border-amber-200">
        <AlertTriangle size={9} /> Estimate
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
      <CheckCircle size={9} /> Real
    </span>
  );
};

// ── Formatting helpers ─────────────────────────────────────────────────────

const fmtUnits = (n: number) =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n);

// ── Main page ──────────────────────────────────────────────────────────────

export const InventoryPage = () => {
  const industry = useWorkspaceIndustry();
  const qc = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");
  const images = useProductImagesStore((s) => s.images);

  // ── Data fetching ────────────────────────────────────────────────────────
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["inventory-levels", industry],
    queryFn: () => inventoryApi.levels(),
    staleTime: 60_000,
  });

  // SKU list is needed to map sku_code → sku_id during CSV import
  const { data: skuData } = useQuery({
    queryKey: ["skus-list", industry],
    queryFn: () => skusApi.list(),
    staleTime: 5 * 60_000,
  });

  const { data: decisionData } = useQuery({
    queryKey: ["decisions", industry, "open", "inventory-context"],
    queryFn: () => decisionsApi.list({ status: "open", limit: 500 }),
    staleTime: 60_000,
  });

  const decisionBySku = useMemo(() => {
    const priority: Record<Decision["urgency"], number> = { critical: 4, high: 3, normal: 2, low: 1 };
    return (decisionData?.decisions ?? []).reduce((bySku, decision) => {
      const current = bySku.get(decision.sku_id);
      const decisionRank = priority[decision.urgency] + (decision.kind === "purchase_order" ? 10 : 0);
      const currentRank = current ? priority[current.urgency] + (current.kind === "purchase_order" ? 10 : 0) : -1;
      if (!current || decisionRank > currentRank) bySku.set(decision.sku_id, decision);
      return bySku;
    }, new Map<string, Decision>());
  }, [decisionData?.decisions]);

  const skuCodeToId = useMemo(() => {
    const map: Record<string, string> = {};
    // skusApi.list() returns Sku[] directly
    (Array.isArray(skuData) ? skuData : []).forEach((s: { sku_code: string; id: string }) => {
      map[s.sku_code] = s.id;
    });
    return map;
  }, [skuData]);

  // ── Derived stats ────────────────────────────────────────────────────────
  const levels = data?.levels ?? [];
  const filtered = useMemo(() => {
    if (!search.trim()) return levels;
    const q = search.toLowerCase();
    return levels.filter(
      (l) => l.sku_code.toLowerCase().includes(q) || l.location.toLowerCase().includes(q),
    );
  }, [levels, search]);

  const totalOnHand = levels.reduce((s, l) => s + l.on_hand_units, 0);
  const totalInbound = levels.reduce((s, l) => s + l.inbound_units, 0);
  const totalAvailable = levels.reduce((s, l) => s + l.available_units, 0);
  const contextualStatus = (level: InventoryLevel) => {
    const decision = decisionBySku.get(level.sku_id);
    return classifyCoverageWithContext(level, decision ? {
      daysOfCover: decision.inputs.days_of_cover,
      leadTimeDays: decision.inputs.lead_time_days,
    } : undefined);
  };
  const nCritical = levels.filter((level) => contextualStatus(level) === "critical").length;
  const nLow = levels.filter((level) => contextualStatus(level) === "low").length;
  const nEstimate = levels.filter((l) => l.source === "seed" || l.source === "fallback").length;
  const hasEstimates = nEstimate > 0;

  // ── CSV import handlers ───────────────────────────────────────────────────
  const handleParse = async (file: File) => {
    const parsed = await parseFile(file);
    const validation = validateInventoryRows(parsed.rows, skuCodeToId);
    return { parsed, validation };
  };

  const handleImport = async (
    rows: ParsedRow[],
    onProgress: (done: number, total: number) => void,
  ): Promise<ImportResult> => {
    const BATCH = 100;
    let created = 0;
    let failed = 0;
    const errors: ImportResult["errors"] = [];

    for (let i = 0; i < rows.length; i += BATCH) {
      const batch = rows.slice(i, i + BATCH);
      const items: InventoryUpsertItem[] = batch.map((row) => ({
        sku_id: skuCodeToId[row.sku_code.trim()],
        on_hand_units: Number(row.on_hand_units),
        inbound_units: row.inbound_units ? Number(row.inbound_units) : 0,
        reserved_units: row.reserved_units ? Number(row.reserved_units) : 0,
        location: row.location?.trim() || "default",
        source: "csv",
      }));
      try {
        const res = await inventoryApi.upsert(items);
        created += res.upserted;
      } catch (e) {
        failed += batch.length;
        errors.push({ row: {}, reason: String(e) });
      }
      onProgress(Math.min(i + BATCH, rows.length), rows.length);
    }

    qc.invalidateQueries({ queryKey: ["inventory-levels"] });
    qc.invalidateQueries({ queryKey: ["cost-analysis"] });
    return { created, skipped: 0, failed, errors };
  };

  if (isLoading) return <PageLoader />;

  return (
    <div className="space-y-4">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-[var(--accent)] text-xs font-semibold uppercase tracking-[0.12em]">
            <Warehouse size={14} /> Inventory
          </div>
          <h1 className="mt-1 font-heading text-3xl font-semibold tracking-tight text-content">Know what needs action</h1>
          <p className="mt-1 text-sm text-content-muted">
            Stock, cover, and the next planning decision in one place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-content-muted transition hover:border-line-strong hover:text-content disabled:opacity-50"
          >
            <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            onClick={() => exportApi.inventoryCsv().catch(() => toast.error("Export failed"))}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium text-content transition hover:bg-surface-2"
          >
            <Upload size={13} />
            Export CSV
          </button>
          <button
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white transition hover:brightness-95"
          >
            <Upload size={13} />
            Import CSV
          </button>
        </div>
      </div>

      {/* ── Estimate warning banner ─────────────────────────────────────────── */}
      {hasEstimates && (
        <div className="flex items-start gap-3 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3">
          <AlertTriangle size={16} className="text-amber-500 mt-0.5 shrink-0" />
          <div>
            <span className="font-semibold text-amber-800 text-sm">
              {nEstimate} SKU{nEstimate !== 1 ? "s" : ""} running on estimated stock
            </span>
            <p className="text-amber-700 text-xs mt-0.5">
              These rows use <code className="font-mono bg-amber-100 px-1 rounded">safety_stock × 2</code> as a
              placeholder. Import real warehouse data via CSV or connect your WMS to fix shortage
              alerts and coverage-days for those SKUs.
            </p>
          </div>
        </div>
      )}

      {/* ── KPI strip ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KPICard
          label="Total On-Hand"
          value={fmtUnits(totalOnHand)}
          icon={<Package size={16} />}
          tone="default"
        />
        <KPICard
          label="Available (net reserved)"
          value={fmtUnits(totalAvailable)}
          icon={<CheckCircle size={16} />}
          tone="default"
        />
        <KPICard
          label="Inbound"
          value={fmtUnits(totalInbound)}
          icon={<TrendingDown size={16} />}
          tone="default"
        />
        <KPICard
          label="At Risk"
          value={`${nCritical} critical · ${nLow} low`}
          icon={<AlertTriangle size={16} />}
          tone={nCritical > 0 ? "danger" : nLow > 0 ? "warning" : "default"}
        />
      </div>

      {/* ── Stock table ────────────────────────────────────────────────────── */}
      <Card
        title={`Stock decisions (${filtered.length})`}
        description="Each row answers three questions: what do we have, why does it matter, and what should happen next?"
      >
        {/* Search */}
        <div className="mb-4 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by SKU code or location…"
            className="w-full rounded-lg border border-line bg-surface py-2 pl-9 pr-3 text-sm text-content placeholder:text-content-subtle focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-emerald-200/50"
          />
        </div>

        {levels.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="h-14 w-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
              <Warehouse size={24} className="text-slate-400" />
            </div>
            <p className="font-semibold text-slate-600">No stock data yet</p>
            <p className="text-sm text-slate-400 mt-1 max-w-xs">
              Import a CSV with your warehouse quantities to power shortage alerts and coverage insights.
            </p>
            <button
              onClick={() => setImportOpen(true)}
              className="mt-4 flex items-center gap-2 text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 rounded-lg px-4 py-2 transition-colors"
            >
              <Upload size={14} />
              Import inventory
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {[
                    "Product / SKU",
                    "Available",
                    "Inbound",
                    "Cover & status",
                    "Why it matters",
                    "Next action",
                  ].map((h) => (
                    <th key={h} className="text-left py-2.5 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((lvl) => {
                  const decision = decisionBySku.get(lvl.sku_id);
                  const status = classifyCoverageWithContext(lvl, decision ? {
                    daysOfCover: decision.inputs.days_of_cover,
                    leadTimeDays: decision.inputs.lead_time_days,
                  } : undefined);
                  const cover = decision?.inputs.days_of_cover;
                  const img = getProductImage(lvl.sku_id, industry, images, lvl.sku_code);
                  return (
                    <tr key={`${lvl.sku_id}-${lvl.location}`} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-3">
                        <div className="flex min-w-[190px] items-center gap-3">
                          <img src={img} alt="" className="h-11 w-11 rounded-lg border border-line bg-surface-2 object-cover" />
                          <div><p className="font-mono text-xs font-semibold text-content">{lvl.sku_code}</p><p className="mt-0.5 text-[11px] text-content-subtle">{lvl.location} · <SourceBadge source={lvl.source} /></p></div>
                        </div>
                      </td>
                      <td className="py-3 px-3 font-bold tabular-nums">
                        <span className={clsx(
                          status === "critical" && "text-red-600",
                          status === "low" && "text-amber-600",
                          status === "healthy" && "text-emerald-600",
                          status === "unknown" && "text-slate-400",
                        )}>
                          {fmtUnits(lvl.available_units)}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-mono text-sm text-emerald-600">{lvl.inbound_units > 0 ? `+${fmtUnits(lvl.inbound_units)}` : "—"}</td>
                      <td className="py-3 px-3"><div className="flex min-w-[130px] flex-col items-start gap-1"><StatusBadge status={status} /><span className="text-xs text-content-muted">{typeof cover === "number" ? `${cover.toFixed(0)} days cover` : "Cover pending"}</span></div></td>
                      <td className="max-w-[320px] py-3 px-3 text-xs leading-5 text-content-muted">
                        {decision?.reasons[0]?.text ?? (status === "healthy" ? "Stock is above the immediate risk threshold." : "Available stock is below the operating buffer.")}
                      </td>
                      <td className="py-3 px-3">
                        {decision ? <Link to="/workspace/decisions" className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-[var(--accent)]">{decision.headline}<ArrowRight size={12} /></Link> : <span className="text-xs text-content-subtle">No action</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Legend */}
        {levels.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-4 pt-4 border-t border-slate-100">
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Info size={11} className="text-slate-400" />
              <span className="font-semibold text-slate-600">Available</span> = on-hand − reserved
            </div>
            <div className="flex items-center gap-3 ml-auto">
              {Object.entries(STATUS_CONFIG)
                .filter(([k]) => k !== "unknown" && k !== "overstock")
                .map(([key, cfg]) => (
                  <div key={key} className="flex items-center gap-1.5 text-xs text-slate-500">
                    <span className={clsx("h-2 w-2 rounded-full", cfg.dot)} />
                    {cfg.label}
                  </div>
                ))}
            </div>
          </div>
        )}
      </Card>

      {/* ── Import modal ────────────────────────────────────────────────────── */}
      <ImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import warehouse stock"
        description="Upload current on-hand quantities from your WMS or ERP export"
        requiredColumns={INVENTORY_REQUIRED_COLUMNS}
        optionalColumns={INVENTORY_OPTIONAL_COLUMNS}
        tip='Each row upserts the position for that SKU. Re-importing the same SKU updates its quantity — no duplicates.'
        onParse={handleParse}
        onImport={handleImport}
        onDownloadTemplate={downloadInventoryTemplate}
      />
    </div>
  );
};
