import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Warehouse, Upload, RefreshCw, Search, ChevronDown, ChevronRight, Trash2 } from "@/components/ui/icons";
import { format, parseISO } from "date-fns";
import toast from "react-hot-toast";
import clsx from "clsx";

import { inventoryApi, validateInventoryRows, downloadInventoryTemplate } from "@/api/inventory";
import type { InventoryAttention, InventoryLevel, InventorySort, InventoryUpsertItem, LocationCoverage, SkuCoverage } from "@/api/inventory";
import { exportApi } from "@/api/export";
import { skusApi } from "@/api/skus";
import { parseFile } from "@/utils/csvImport";
import type { ParsedRow } from "@/utils/csvImport";
import { ImportModal } from "@/components/ui/ImportModal";
import type { ImportResult } from "@/components/ui/ImportModal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageLoader } from "@/components/ui/Spinner";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { invalidatePlanningData } from "@/api/planningKeys";
import { useAuthStore } from "@/stores/auth";
import { getErrorMessage } from "@/utils/errors";

const PAGE_SIZE = 25;
const REQUIRED_COLUMNS = ["sku_code", "on_hand_units"] as const;
const OPTIONAL_COLUMNS = ["inbound_units", "reserved_units", "location"] as const;
const fmt = (n: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(n);
type Attention = "all" | "needs" | "excess" | "unknown";
const controls = "rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-content transition hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] disabled:opacity-40";

function storeStatus(cov: LocationCoverage | undefined) {
  if (cov?.status === "healthy" && cov.location_demand?.weekly_units === 0) return "healthy";
  if (cov?.cover_days == null || cov.status == null) return "unknown";
  return cov.status;
}

function StoreDetail({ level, cov, sku, recommendation }: { level: InventoryLevel; cov: LocationCoverage | undefined; sku: SkuCoverage | undefined; recommendation: string | undefined }) {
  const status = storeStatus(cov);
  const labels = { critical: "Needs stock soon", low: "Running low", healthy: "Enough stock", excess: "Overstock", unknown: "Missing data" };
  const sourceNames: Record<string, string> = { csv: "CSV import", upload: "File upload", manual: "Manual entry", api: "API push", fallback: "Estimate", synthetic_test: "Test fixture" };
  return <section className="rounded-xl border border-line bg-surface p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="font-semibold text-content">{level.location}</h3>
      <span className={clsx("whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold", status === "critical" ? "bg-red-50 text-red-700" : status === "low" ? "bg-amber-50 text-amber-800" : status === "excess" ? "bg-blue-50 text-blue-700" : status === "healthy" ? "bg-emerald-50 text-emerald-700" : "bg-surface-2 text-content-muted")}>{labels[status]}</span>
    </div>
    <p className="mt-1 text-xs text-content-muted">{sourceNames[level.source] ?? `${level.source} sync`} · {level.as_of ? `as of ${format(parseISO(level.as_of), "d MMM yyyy")}` : "No observation date"}</p>
    <dl className="my-4 grid grid-cols-3 gap-3 text-sm">
      <div><dt className="text-xs text-content-muted">Available</dt><dd className="mt-1 font-mono font-semibold">{fmt(level.available_units)}</dd></div>
      <div><dt className="text-xs text-content-muted">Arriving</dt><dd className="mt-1 font-mono font-semibold">{fmt(level.inbound_units)}</dd></div>
      <div><dt className="text-xs text-content-muted">Reserved</dt><dd className="mt-1 font-mono font-semibold">{fmt(level.reserved_units)}</dd></div>
    </dl>
    <p className="text-sm font-medium">{cov?.cover_days != null ? cov.demand_basis === "period_average" ? `Estimated stock cover: ${cov.cover_days} days` : `Stock lasts ${cov.cover_days} days` : status === "healthy" && cov?.location_demand?.weekly_units === 0 ? "No sales expected in this forecast window" : "Store cover unknown"}</p>
    <p className="mt-1 text-xs text-content-muted">{cov?.reason || "Add sales tagged to this store to calculate its cover."}</p>
    {cov?.degraded && <p className="mt-2 text-xs text-amber-800">Location split incomplete: {cov.unassigned_share == null ? "Unknown share" : `${Math.round(cov.unassigned_share * 100)}% of sales`} has no location.</p>}
    <div className="mt-3 border-t border-line pt-3 text-sm font-semibold text-[var(--accent)]">
      {recommendation ? <Link to="/workspace/decisions">{recommendation}</Link>
        : cov?.open_transfer ? <Link to="/workspace/decisions">Review transfer of {cov.open_transfer.units} to {cov.open_transfer.destination}</Link>
        : cov?.next_action ? <p>{cov.next_action}</p>
        : status === "critical" || status === "low" ? <Link to="/workspace/decisions">Review shortage</Link>
        : status === "excess" ? <p>Review excess stock and incoming orders</p>
        : status === "unknown" ? <p>Review sales and stock data</p>
        : <p>Keep monitoring</p>}
    </div>
    {sku && <details className="mt-3 text-xs text-content-muted"><summary className="cursor-pointer">How this is calculated</summary>
      <p className="mt-2">{cov?.demand_basis === "forecast" ? "Based on this store’s forecast." : cov?.demand_basis === "trailing_actuals" ? "Based on this store’s uploaded sales." : cov?.demand_basis === "period_average" ? "Based on this store’s reported period average. Assumes an unchanged daily selling rate; confirm stock date and lead time before ordering." : "A store demand estimate is not available."} Replenishment time: {sku.lead_time_days} days{sku.lead_time_assumed ? " (assumed)" : ""}.</p>
      {sku.sku_wide.cover_days != null && <p className="mt-1">All-store pooled cover: {sku.sku_wide.cover_days} days. This does not describe this store’s cover.</p>}
    </details>}
  </section>;
}

export const InventoryPage = () => {
  const tenantId = useAuthStore((state) => state.tenantId);
  const industry = useWorkspaceIndustry();
  return <InventoryWorkspace key={`${tenantId}:${industry}`} />;
};

const InventoryWorkspace = () => {
  const industry = useWorkspaceIndustry();
  const tenantId = useAuthStore((state) => state.tenantId);
  const qc = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [location, setLocation] = useState("");
  const [offset, setOffset] = useState(0);
  const [attention, setAttention] = useState<Attention>("all");
  const [sort, setSort] = useState<InventorySort>("sku");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [skuCodeToId, setSkuCodeToId] = useState<Record<string, string>>({});
  const [selectedSkuIds, setSelectedSkuIds] = useState<Set<string>>(new Set());
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const [confirmDeleteSelected, setConfirmDeleteSelected] = useState(false);

  const toggleSelectSku = (id: string) => {
    setSelectedSkuIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const deleteAllMutation = useMutation({
    mutationFn: () => inventoryApi.deleteAll(),
    onSuccess: (res) => {
      toast.success(`Cleared all ${res.deleted} stock positions`);
      setSelectedSkuIds(new Set());
      setConfirmDeleteAll(false);
      void refresh();
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Failed to clear stock"));
      setConfirmDeleteAll(false);
    },
  });

  const deleteSelectedMutation = useMutation({
    mutationFn: () => inventoryApi.deleteMany(Array.from(selectedSkuIds)),
    onSuccess: (res) => {
      toast.success(`Deleted ${res.deleted} stock position${res.deleted !== 1 ? "s" : ""}`);
      setSelectedSkuIds(new Set());
      setConfirmDeleteSelected(false);
      void refresh();
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Failed to delete selected stock"));
      setConfirmDeleteSelected(false);
    },
  });

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ["inventory-levels", "overview", tenantId, industry, search, location, attention, sort, offset],
    queryFn: () => inventoryApi.overview({ offset, limit: PAGE_SIZE, search, location, attention, sort }), staleTime: 60_000,
    placeholderData: (previous, query) => query?.queryKey[2] === tenantId && query.queryKey[3] === industry ? previous : undefined,
  });
  const coverage = useMemo(() => new Map((data?.coverage.skus ?? []).map((s) => [s.sku_id, s])), [data?.coverage.skus]);
  const rows = useMemo(() => (data?.skus ?? []).map((sku) => {
    const levels = data?.levels.filter((level) => level.sku_id === sku.sku_id) ?? [];
    const cov = coverage.get(sku.sku_id);
    const states = levels.map((level) => storeStatus(cov?.locations.find((c) => c.location === level.location)));
    return { ...sku, levels, cov, needs: states.filter((s) => s === "critical" || s === "low").length,
      excess: states.filter((s) => s === "excess").length, unknown: states.filter((s) => s === "unknown").length };
  }), [data?.skus, data?.levels, coverage]);
  const filtered = rows;
  const isTrulyEmpty = !isError && data?.total_skus === 0 && !search && !location;
  const assumed = [...new Set(rows.filter((r) => r.cov?.lead_time_assumed).map((r) => r.cov!.lead_time_days))];
  const refresh = () => invalidatePlanningData(qc);
  const toggle = (id: string) => setExpanded((prior) => { const next = new Set(prior); if (next.has(id)) next.delete(id); else next.add(id); return next; });

  const allPageIds = useMemo(() => filtered.map((r) => r.sku_id), [filtered]);
  const isAllSelected = allPageIds.length > 0 && allPageIds.every((id) => selectedSkuIds.has(id));
  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedSkuIds((prev) => {
        const next = new Set(prev);
        allPageIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelectedSkuIds((prev) => {
        const next = new Set(prev);
        allPageIds.forEach((id) => next.add(id));
        return next;
      });
    }
  };

  const handleParse = async (file: File) => {
    const parsed = await parseFile(file);
    // Read catalogue pages only during import, stopping once this file is resolved.
    const needed = new Set(parsed.rows.map((row) => row.sku_code?.trim()).filter(Boolean));
    const map: Record<string, string> = {};
    for (let start = 0; ; start += 200) {
      const page = await skusApi.list({ limit: 200, offset: start, active_only: false });
      for (const sku of page) if (needed.has(sku.sku_code)) map[sku.sku_code] = sku.id;
      if (page.length < 200 || Object.keys(map).length === needed.size) break;
    }
    setSkuCodeToId(map);
    return { parsed, validation: validateInventoryRows(parsed.rows, map) };
  };
  const handleImport = async (rowsToImport: ParsedRow[], onProgress: (done: number, total: number) => void): Promise<ImportResult> => {
    let created = 0; let failed = 0;
    const errors: ImportResult["errors"] = [];
    for (let i = 0; i < rowsToImport.length; i += 100) {
      const batch = rowsToImport.slice(i, i + 100);
      const items: InventoryUpsertItem[] = batch.map((row) => ({ sku_id: skuCodeToId[row.sku_code.trim()], on_hand_units: Number(row.on_hand_units), inbound_units: Number(row.inbound_units || 0), reserved_units: Number(row.reserved_units || 0), location: row.location?.trim() || "default", source: "csv" }));
      try { created += (await inventoryApi.upsert(items)).upserted; }
      catch (error) { failed += batch.length; errors.push({ row: {}, reason: String(error) }); }
      onProgress(Math.min(i + 100, rowsToImport.length), rowsToImport.length);
    }
    await refresh();
    return { created, skipped: 0, failed, errors };
  };
  if (isLoading) return <PageLoader />;
  return <div className="space-y-5">
    <header className="flex flex-col justify-between gap-4 rounded-2xl border border-line bg-surface p-5 xl:flex-row xl:items-center">
      <div><p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-[var(--accent)]"><Warehouse size={15} />Stock overview</p>
        <h1 className="mt-2 font-heading text-2xl font-semibold text-content">Inventory</h1>
        <p className="mt-1 max-w-lg text-sm text-content-muted">See what you have, where it is, and which stores need attention.</p></div>
      <div className="flex flex-wrap gap-2">
        <button onClick={() => void refresh()} disabled={isFetching} className={controls}><span className="flex items-center gap-2"><RefreshCw size={14} />Refresh</span></button>
        <button onClick={() => void exportApi.inventoryCsv().catch(() => toast.error("Export failed"))} className={controls}>Export CSV</button>
        {!isTrulyEmpty && <button onClick={() => setImportOpen(true)} className={`${controls} !bg-[var(--accent)] !text-accent-fg`}>Import stock</button>}
        <button
          onClick={() => setConfirmDeleteAll(true)}
          disabled={!data?.total_positions || isFetching}
          className={`${controls} text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/20 flex items-center gap-1.5`}
        >
          <Trash2 size={14} /> Clear stock
        </button>
      </div>
    </header>
    {isError ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-800">Stock could not be loaded. Refresh to try again; an empty position has not been confirmed.</div>
      : isTrulyEmpty ? <section className="rounded-2xl border border-line bg-surface p-6 sm:p-8">
        <Warehouse size={30} className="text-[var(--accent)]" />
        <h2 className="mt-4 font-heading text-xl font-semibold">Build your stock picture</h2>
        <p className="mt-2 max-w-xl text-sm text-content-muted">Start with your catalogue, add sales history, then upload the quantities at each store. Your own data will appear here.</p>
        <ol className="mt-6 grid gap-3 lg:grid-cols-3">
          <li className="rounded-xl border border-line p-4"><p className="text-xs text-content-muted">01 · Catalogue</p><Link className="mt-2 block font-semibold text-[var(--accent)]" to="/workspace/products">Add products and SKUs</Link><p className="mt-1 text-sm text-content-muted">Give every variant a unique SKU code.</p></li>
          <li className="rounded-xl border border-line p-4"><p className="text-xs text-content-muted">02 · Demand</p><Link className="mt-2 block font-semibold text-[var(--accent)]" to="/workspace/integrations">Add sales history</Link><p className="mt-1 text-sm text-content-muted">Include store names to calculate local stock cover.</p></li>
          <li className="rounded-xl border border-line p-4"><p className="text-xs text-content-muted">03 · Stock</p><button onClick={() => setImportOpen(true)} className="mt-2 flex items-center gap-2 font-semibold text-[var(--accent)]"><Upload size={15} />Import stock</button><p className="mt-1 text-sm text-content-muted">Upload on-hand, reserved and arriving quantities.</p></li>
        </ol>
      </section> : <>
        <section className="grid gap-3 sm:grid-cols-3" aria-label="Stock totals for current search and location">
          <div className="rounded-xl border border-line bg-surface p-4"><p className="text-xs text-content-muted">Stock in scope</p><p className="mt-2 font-semibold">{data?.total_skus ?? 0} SKUs · {data?.total_positions ?? 0} stock positions</p></div>
          <div className="rounded-xl border border-line bg-surface p-4"><p className="text-xs text-content-muted">Available units</p><p className="mt-2 font-mono text-xl font-semibold">{fmt(data?.totals.available_units ?? 0)}</p><p className="mt-1 text-xs text-content-muted">After reservations</p></div>
          <div className="rounded-xl border border-line bg-surface p-4"><p className="text-xs text-content-muted">Arriving units</p><p className="mt-2 font-mono text-xl font-semibold">{fmt(data?.totals.inbound_units ?? 0)}</p></div>
        </section>
        <section className="rounded-2xl border border-line bg-surface p-4 sm:p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-end">
            <label className="flex-1 text-xs font-semibold text-content-muted">Search stock<div className="relative mt-1.5"><Search size={15} className="absolute left-3 top-3 text-content-muted" /><input aria-label="Search stock" type="search" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} placeholder="Product, SKU or store" className={`${controls} w-full pl-9 font-normal`} /></div></label>
            <label className="text-xs font-semibold text-content-muted">Location<select aria-label="Location" value={location} onChange={(e) => { setLocation(e.target.value); setOffset(0); }} className={`${controls} mt-1.5 block min-w-44`}><option value="">All locations</option>{data?.locations.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
          </div>
          <div className="my-4 flex flex-wrap items-center gap-2" aria-label="Attention filters across all results"><span className="mr-1 text-xs text-content-muted">All results</span>{([["all", "All"], ["needs", "Needs stock"], ["excess", "Overstock"], ["unknown", "Missing data"]] as const).map(([value, label]) => <button key={value} aria-pressed={attention === value} onClick={() => { setAttention(value as InventoryAttention); setOffset(0); }} className={clsx(controls, "!rounded-full !px-3 !py-1.5 !text-xs", attention === value && "!border-[var(--accent)] !bg-[var(--accent)] !text-accent-fg")}>{label}</button>)}<label className="ml-auto text-xs font-semibold text-content-muted">Sort<select aria-label="Sort inventory" value={sort} onChange={(e) => { setSort(e.target.value as InventorySort); setOffset(0); }} className={`${controls} ml-2`}><option value="sku">SKU</option><option value="available_asc">Available: low to high</option><option value="available_desc">Available: high to low</option><option value="freshness">Freshest update</option></select></label></div>
          {assumed.length > 0 && <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">Replenishment time assumed: {assumed.join(", ")} days for some SKUs on this page. Add supplier lead times for more precise warnings.</p>}
          {rows.some(row => row.cov?.demand.basis === "period_average" || row.cov?.locations.some(loc => loc.demand_basis === "period_average")) && <p className="mb-4 rounded-lg border border-line px-3 py-3 text-xs text-content-muted">Average-sales estimates are used where dated SKU history is unavailable. Store cover assumes the reported period average continues. Confirm stock dates and supplier lead times before acting; these estimates do not generate purchase or transfer decisions.</p>}
          {selectedSkuIds.size > 0 && (
            <div className="flex items-center justify-between rounded-xl bg-accent/10 border border-accent/20 px-4 py-2.5 mb-4 text-sm">
              <span className="font-medium text-content">
                {selectedSkuIds.size} SKU position{selectedSkuIds.size !== 1 ? "s" : ""} selected
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedSkuIds(new Set())}
                  className="text-xs text-content-muted hover:text-content underline px-2 py-1"
                >
                  Deselect all
                </button>
                <button
                  onClick={() => setConfirmDeleteSelected(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-sm transition"
                >
                  <Trash2 size={13} />
                  Delete Selected
                </button>
              </div>
            </div>
          )}
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-line text-left text-xs text-content-muted">
            <th className="py-3 pl-3 pr-2 w-8">
              <input
                type="checkbox"
                aria-label="Select all SKUs on page"
                checked={isAllSelected}
                onChange={toggleSelectAll}
                className="h-4 w-4 rounded border-line text-[var(--accent)] focus:ring-[var(--accent)] cursor-pointer"
              />
            </th>
            <th className="py-3 pr-4 font-medium">Product / SKU</th><th className="px-3 py-3 font-medium">Available</th><th className="px-3 py-3 font-medium">Arriving</th><th className="py-3 pl-3 font-medium">Store attention</th></tr></thead>
            <tbody className="divide-y divide-line">{filtered.map((row) => <Fragment key={row.sku_id}>
              <tr>
                <td className="py-4 pl-3 pr-2 w-8">
                  <input
                    type="checkbox"
                    aria-label={`Select ${row.sku_code}`}
                    checked={selectedSkuIds.has(row.sku_id)}
                    onChange={() => toggleSelectSku(row.sku_id)}
                    className="h-4 w-4 rounded border-line text-[var(--accent)] focus:ring-[var(--accent)] cursor-pointer"
                  />
                </td>
                <td className="py-4 pr-4">{location ? <span><span className="block font-semibold text-content">{row.product_name}</span><span className="mt-1 block font-mono text-xs text-content-muted">{row.sku_code}</span></span> : <button aria-expanded={expanded.has(row.sku_id)} aria-controls={`stores-${row.sku_id}`} aria-label={`${expanded.has(row.sku_id) ? "Hide" : "Show"} stores for ${row.sku_code}`} onClick={() => toggle(row.sku_id)} className="flex items-center gap-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]">{expanded.has(row.sku_id) ? <ChevronDown size={15} /> : <ChevronRight size={15} />}<span><span className="block font-semibold text-content">{row.product_name}</span><span className="mt-1 block font-mono text-xs text-content-muted">{row.sku_code}</span></span></button>}</td>
                <td className="px-3 py-4 font-mono">{fmt(row.levels.reduce((sum, l) => sum + l.available_units, 0))}</td><td className="px-3 py-4 font-mono">{fmt(row.levels.reduce((sum, l) => sum + l.inbound_units, 0))}</td>
                <td className="py-4 pl-3 text-xs"><div className="space-y-1">{row.needs > 0 && <p className="font-semibold text-red-700">{row.needs} {row.needs === 1 ? "store needs" : "stores need"} stock</p>}{row.excess > 0 && <p className="text-blue-700">{row.excess} {row.excess === 1 ? "store has" : "stores have"} overstock</p>}{row.unknown > 0 && <p className="text-content-muted">{row.unknown} {row.unknown === 1 ? "store needs" : "stores need"} data</p>}{!row.needs && !row.excess && !row.unknown && <p className="text-emerald-700">Enough stock at {row.levels.length} {row.levels.length === 1 ? "store" : "stores"}</p>}</div></td></tr>
              {(expanded.has(row.sku_id) || location) && <tr id={`stores-${row.sku_id}`}><td colSpan={5} className="pb-4"><div className="grid gap-3 bg-surface-2 p-3 xl:grid-cols-2">{row.levels.map((level) => <StoreDetail key={level.location} level={level} cov={row.cov?.locations.find((c) => c.location === level.location)} sku={row.cov} recommendation={data?.recommendations?.find((r) => r.sku_id === row.sku_id && r.location?.trim().toLowerCase() === level.location.trim().toLowerCase())?.headline} />)}</div></td></tr>}
            </Fragment>)}</tbody></table></div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4"><p className="text-xs text-content-muted">{(data?.total_skus ?? 0) > 0 ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, data!.total_skus)} of ${data!.total_skus} matching SKUs` : "0 matching SKUs"} · Filters apply across the full result set.</p><div className="flex gap-2"><button aria-label="Previous page" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0 || isFetching} className={controls}>Previous</button><button aria-label="Next page" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={offset + PAGE_SIZE >= (data?.total_skus ?? 0) || isFetching} className={controls}>Next</button></div></div>
        </section>
      </>}
    <ImportModal open={importOpen} onClose={() => setImportOpen(false)} title="Import warehouse stock" description="Upload current quantities for each SKU and store" requiredColumns={REQUIRED_COLUMNS} optionalColumns={OPTIONAL_COLUMNS} tip="Use the same store names as your sales history. Re-importing updates the existing SKU/store position." onParse={handleParse} onImport={handleImport} onDownloadTemplate={downloadInventoryTemplate} />

    <ConfirmDialog
      open={confirmDeleteAll}
      onClose={() => setConfirmDeleteAll(false)}
      title="Clear All Stock Positions"
      tone="danger"
      loading={deleteAllMutation.isPending}
      confirmLabel="Delete All Stock"
      message={
        <p>
          Are you sure you want to delete ALL inventory stock positions for the <strong>{industry}</strong> industry? This action cannot be undone.
        </p>
      }
      onConfirm={() => deleteAllMutation.mutate()}
    />

    <ConfirmDialog
      open={confirmDeleteSelected}
      onClose={() => setConfirmDeleteSelected(false)}
      title="Delete Selected Stock Positions"
      tone="danger"
      loading={deleteSelectedMutation.isPending}
      confirmLabel={`Delete ${selectedSkuIds.size} Stock Position${selectedSkuIds.size !== 1 ? "s" : ""}`}
      message={
        <p>
          Are you sure you want to delete stock positions for <strong>{selectedSkuIds.size}</strong> selected SKU(s)? This action cannot be undone.
        </p>
      }
      onConfirm={() => deleteSelectedMutation.mutate()}
    />
  </div>;
};
