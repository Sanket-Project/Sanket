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
import { format, parseISO } from "date-fns";

import { inventoryApi, validateInventoryRows, downloadInventoryTemplate } from "@/api/inventory";
import { exportApi } from "@/api/export";
import toast from "react-hot-toast";
import type { InventoryLevel, InventoryUpsertItem, SkuCoverage } from "@/api/inventory";
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
import { invalidatePlanningData } from "@/api/planningKeys";

// ── Coverage classification ────────────────────────────────────────────────

const INVENTORY_REQUIRED_COLUMNS = ["sku_code", "on_hand_units"] as const;
const INVENTORY_OPTIONAL_COLUMNS = ["inbound_units", "reserved_units", "location"] as const;

type CoverageStatus = "healthy" | "low" | "critical" | "excess" | "unknown" | "unavailable";

/**
 * What a stock row shows, straight from /inventory/coverage: the location's
 * own cover when its sales support one, otherwise the SKU-wide (pooled) cover
 * labelled as such, otherwise unknown with the reason. Never a fixed unit
 * threshold, and never dependent on whether a recommendation exists.
 */
function rowCoverage(sku: SkuCoverage | undefined, location: string, failed = false) {
  if (failed) {
    return {
      status: "unavailable" as CoverageStatus,
      label: "Cover could not be loaded",
      reason: "Coverage service unavailable — retry with Refresh. No status is inferred.",
    };
  }
  if (!sku) {
    return { status: "unknown" as CoverageStatus, label: "Cover unknown", reason: "No coverage data for this SKU yet." };
  }
  const loc = sku.locations.find((l) => l.location === location);
  if (loc?.status && loc.cover_days != null) {
    return {
      status: loc.status as CoverageStatus,
      label: `Store cover ${loc.cover_days} days`,
      reason: loc.reason,
      nextAction: loc.next_action ?? null,
    };
  }
  if (sku.sku_wide.status !== "unknown" && sku.sku_wide.cover_days != null) {
    return {
      status: sku.sku_wide.status as CoverageStatus,
      label: `SKU-wide cover ${sku.sku_wide.cover_days} days (all locations)`,
      reason: loc?.reason ?? sku.sku_wide.reason,
      nextAction: sku.sku_wide.next_action ?? null,
    };
  }
  if (sku.sku_wide.status === "healthy") {
    return { status: "healthy" as CoverageStatus, label: "No sales expected", reason: sku.sku_wide.reason };
  }
  return { status: "unknown" as CoverageStatus, label: "Cover unknown", reason: sku.sku_wide.reason };
}

const STATUS_CONFIG: Record<CoverageStatus, { label: string; classes: string; dot: string }> = {
  healthy:   { label: "Healthy",    classes: "bg-emerald-50 text-emerald-700 border-emerald-200",  dot: "bg-emerald-400" },
  low:       { label: "Low",        classes: "bg-amber-50 text-amber-700 border-amber-200",        dot: "bg-amber-400"   },
  critical:  { label: "Critical",   classes: "bg-red-50 text-red-700 border-red-200",              dot: "bg-red-500"     },
  excess:    { label: "Excess",     classes: "bg-blue-50 text-blue-700 border-blue-200",           dot: "bg-blue-400"    },
  unknown:   { label: "Unknown",    classes: "bg-slate-50 text-slate-500 border-slate-200",        dot: "bg-slate-300"   },
  unavailable: { label: "Unavailable", classes: "bg-slate-50 text-slate-500 border-slate-200",     dot: "bg-slate-300"   },
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

// ── Provenance — where a stock row came from and when it was observed ──────
// "Real" only meant "not seed/fallback", which says nothing about whether the
// source is authentic; name the source and the as-of date instead.

const SOURCE_LABELS: Record<string, string> = {
  csv: "CSV import",
  upload: "File upload",
  excel: "Excel import",
  manual: "Manual entry",
  api: "API push",
  webhook: "Webhook push",
  fallback: "Estimate (safety stock × 2)",
  synthetic: "Synthetic fixture",
  synthetic_test: "Synthetic fixture",
};

function provenanceLabel(source: string, asOf: string | null): string {
  const known = SOURCE_LABELS[source.toLowerCase()];
  const name = known ?? `${source.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase())} sync`;
  return asOf ? `${name} · as of ${format(parseISO(asOf), "d MMM yyyy")}` : `${name} · no as-of date`;
}

const SourceBadge = ({ source, asOf }: { source: string; asOf: string | null }) => {
  const isEstimate = source === "seed" || source === "fallback";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border",
        isEstimate
          ? "bg-amber-100 text-amber-700 border-amber-200"
          : "bg-surface-2 text-content-muted border-line",
      )}
    >
      {isEstimate && <AlertTriangle size={9} />}
      {provenanceLabel(source, asOf)}
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
  const [locationFilter, setLocationFilter] = useState("");
  const images = useProductImagesStore((s) => s.images);

  // ── Data fetching ────────────────────────────────────────────────────────
  const { data, isLoading, isFetching, isError: levelsFailed } = useQuery({
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

  const { data: coverageData, isError: coverageFailed } = useQuery({
    queryKey: ["inventory-coverage", industry],
    queryFn: () => inventoryApi.coverage(),
    staleTime: 60_000,
  });
  const coverageBySku = useMemo(
    () => new Map((coverageData?.skus ?? []).map((s) => [s.sku_id, s])),
    [coverageData?.skus],
  );

  const { data: decisionData, isError: decisionsFailed } = useQuery({
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
  const levels = useMemo(() => data?.levels ?? [], [data?.levels]);
  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return levels.filter(
      (l) => (!locationFilter || l.location.trim().toLowerCase() === locationFilter.trim().toLowerCase()) &&
        (!search.trim() || l.sku_code.toLowerCase().includes(q) || l.location.toLowerCase().includes(q)),
    );
  }, [levels, search, locationFilter]);
  const locationOptions = [...new Set((coverageData?.skus ?? []).flatMap((sku) => sku.locations.map((l) => l.location)))].sort();

  const totalOnHand = levels.reduce((s, l) => s + l.on_hand_units, 0);
  const totalInbound = levels.reduce((s, l) => s + l.inbound_units, 0);
  const totalAvailable = levels.reduce((s, l) => s + l.available_units, 0);
  const statusOf = (level: InventoryLevel) =>
    rowCoverage(coverageBySku.get(level.sku_id), level.location, coverageFailed).status;
  // Stock, cover and decisions are one picture: refresh them together so cover
  // never describes the previous stock (deep audit F9).
  const refreshAll = () => invalidatePlanningData(qc);
  const nCritical = levels.filter((level) => statusOf(level) === "critical").length;
  const nLow = levels.filter((level) => statusOf(level) === "low").length;
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

    await refreshAll();
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
            onClick={() => void refreshAll()}
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

      {levelsFailed && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <p>
            Stock could not be loaded. The figures below are not a confirmed empty position — use
            Refresh to try again.
          </p>
        </div>
      )}

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
          value={levelsFailed ? "Unavailable" : fmtUnits(totalOnHand)}
          icon={<Package size={16} />}
          tone="default"
        />
        <KPICard
          label="Available (net reserved)"
          value={levelsFailed ? "Unavailable" : fmtUnits(totalAvailable)}
          icon={<CheckCircle size={16} />}
          tone="default"
        />
        <KPICard
          label="Inbound"
          value={levelsFailed ? "Unavailable" : fmtUnits(totalInbound)}
          icon={<TrendingDown size={16} />}
          tone="default"
        />
        <KPICard
          label="At Risk"
          value={levelsFailed || coverageFailed ? "Unavailable" : `${nCritical} critical · ${nLow} low`}
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
        <label className="mb-3 flex items-center gap-2 text-sm">Location
          <select aria-label="Location" value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)}
            className="rounded-lg border border-line bg-surface px-3 py-2 text-content">
            <option value="">All locations</option>
            {locationOptions.map((location) => <option key={location} value={location}>{location}</option>)}
          </select>
        </label>
        <div className="mb-4 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by SKU code or location…"
            className="w-full rounded-lg border border-line bg-surface py-2 pl-9 pr-3 text-sm text-content placeholder:text-content-subtle focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-emerald-200/50"
          />
        </div>

        {levelsFailed ? (
          <p className="py-10 text-center text-sm text-content-muted">
            Stock rows are unavailable until the inventory service responds.
          </p>
        ) : levels.length === 0 ? (
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
                  const skuCov = coverageBySku.get(lvl.sku_id);
                  const cov = rowCoverage(skuCov, lvl.location, coverageFailed);
                  const locationCov = skuCov?.locations.find((l) => l.location === lvl.location);
                  const status = cov.status;
                  const img = getProductImage(lvl.sku_id, industry, images, lvl.sku_code);
                  return (
                    <tr key={`${lvl.sku_id}-${lvl.location}`} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-3">
                        <div className="flex min-w-[190px] items-center gap-3">
                          <img src={img} alt="" className="h-11 w-11 rounded-lg border border-line bg-surface-2 object-cover" />
                          <div><p className="font-mono text-xs font-semibold text-content">{lvl.sku_code}</p><p className="mt-0.5 text-[11px] text-content-subtle">{lvl.location} · <SourceBadge source={lvl.source} asOf={lvl.as_of} /></p></div>
                        </div>
                      </td>
                      <td className="py-3 px-3 font-bold tabular-nums">
                        <span className={clsx(
                          status === "critical" && "text-red-600",
                          status === "low" && "text-amber-600",
                          status === "healthy" && "text-emerald-600",
                          (status === "unknown" || status === "unavailable") && "text-slate-400",
                        )}>
                          {fmtUnits(lvl.available_units)}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-mono text-sm text-emerald-600">{lvl.inbound_units > 0 ? `+${fmtUnits(lvl.inbound_units)}` : "—"}</td>
                      <td className="py-3 px-3"><div className="flex min-w-[130px] flex-col items-start gap-1"><StatusBadge status={status} /><span className="text-xs text-content-muted">{cov.label}</span>{skuCov?.lead_time_assumed && <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">Lead time assumed ({skuCov.lead_time_days}-day default)</span>}</div></td>
                      <td className="max-w-[320px] py-3 px-3 text-xs leading-5 text-content-muted">
                        {cov.reason || decision?.reasons[0]?.text}
                        {locationCov?.demand_basis === "forecast" && <p className="mt-1 text-xs font-medium">From location forecast</p>}
                        {locationCov?.degraded && <p className="mt-1 text-xs font-medium text-amber-700">
                          Location split incomplete: {locationCov.unassigned_share == null ? "Unknown" : Math.round(locationCov.unassigned_share * 100)}% of sales have no location
                        </p>}
                      </td>
                      <td className="py-3 px-3">
                        {locationCov?.open_transfer && <Link to="/workspace/decisions" className="block text-xs font-semibold text-[var(--accent)]">
                          Transfer {locationCov.open_transfer.units} to {locationCov.open_transfer.destination} suggested
                        </Link>}
                        {decision ? (
                          <Link to="/workspace/decisions" className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-[var(--accent)]">{decision.headline}<ArrowRight size={12} /></Link>
                        ) : "nextAction" in cov && cov.nextAction ? (
                          <span className="text-xs font-medium text-content">{cov.nextAction}</span>
                        ) : decisionsFailed || status === "unavailable" ? (
                          <span className="text-xs text-content-subtle">Unavailable — refresh to retry</span>
                        ) : (
                          <span className="text-xs text-content-subtle">No action</span>
                        )}
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
              <span className="font-semibold text-slate-600">Available</span> = on-hand − reserved ·
              Critical = cover at or below lead time · Low = within 1.5× lead time · Excess = cover beyond 2× (lead time + review period) · Unknown = no demand basis or stock older than 30 days
            </div>
            <div className="flex items-center gap-3 ml-auto">
              {Object.entries(STATUS_CONFIG)
                .filter(([k]) => k !== "unavailable")
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
