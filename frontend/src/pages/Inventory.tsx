import { useState, useMemo } from "react";
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
} from "lucide-react";
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
import { useIndustryStore } from "@/stores/industry";

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
  const industry = useIndustryStore((s) => s.activeIndustry);
  const qc = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");

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
  const nCritical = levels.filter((l) => classifyCoverage(l) === "critical").length;
  const nLow = levels.filter((l) => classifyCoverage(l) === "low").length;
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
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
            <Warehouse size={14} /> Inventory
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Warehouse Stock</h1>
          <p className="text-slate-500 mt-1">
            Current on-hand positions that power shortage alerts, coverage, and replenishment insights
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg px-3 py-1.5 bg-white transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            onClick={() => exportApi.inventoryCsv().catch(() => toast.error("Export failed"))}
            className="flex items-center gap-1.5 text-sm font-medium text-slate-700 border border-slate-200 hover:bg-slate-50 rounded-lg px-3 py-1.5 bg-white transition-colors"
          >
            <Upload size={13} />
            Export CSV
          </button>
          <button
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-1.5 text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 rounded-lg px-3 py-1.5 transition-colors"
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
        title={`Stock positions (${filtered.length})`}
        description="On-hand, inbound, and available units per SKU. Alerts and coverage calculations read these figures."
      >
        {/* Search */}
        <div className="mb-4 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by SKU code or location…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-violet-300 focus:border-violet-400"
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
                    "SKU",
                    "Location",
                    "On-Hand",
                    "Inbound",
                    "Reserved",
                    "Available",
                    "Status",
                    "Data source",
                    "As of",
                  ].map((h) => (
                    <th key={h} className="text-left py-2.5 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.map((lvl) => {
                  const status = classifyCoverage(lvl);
                  return (
                    <tr key={`${lvl.sku_id}-${lvl.location}`} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-xs font-semibold text-slate-800">
                        {lvl.sku_code}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500 text-xs">{lvl.location}</td>
                      <td className="py-2.5 px-3 font-medium text-slate-700 tabular-nums">
                        {fmtUnits(lvl.on_hand_units)}
                      </td>
                      <td className="py-2.5 px-3 text-emerald-600 tabular-nums">
                        {lvl.inbound_units > 0 ? `+${fmtUnits(lvl.inbound_units)}` : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 tabular-nums">
                        {lvl.reserved_units > 0 ? fmtUnits(lvl.reserved_units) : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="py-2.5 px-3 font-bold tabular-nums">
                        <span className={clsx(
                          status === "critical" && "text-red-600",
                          status === "low" && "text-amber-600",
                          status === "healthy" && "text-emerald-600",
                          status === "unknown" && "text-slate-400",
                        )}>
                          {fmtUnits(lvl.available_units)}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        <StatusBadge status={status} />
                      </td>
                      <td className="py-2.5 px-3">
                        <SourceBadge source={lvl.source} />
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 text-xs whitespace-nowrap">
                        {lvl.as_of
                          ? new Date(lvl.as_of).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
                          : <span className="text-slate-300">—</span>}
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
