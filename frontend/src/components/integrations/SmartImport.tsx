import { useId, useRef, useState, type DragEvent } from "react";
import toast from "react-hot-toast";
import clsx from "clsx";
import {
  integrationsApi,
  type FilePlan,
  type FilePlanSlot,
  type PlanConfirmResult,
  type PlanDecision,
  type PlanDestination,
  type PlanEvaluation,
} from "@/api/integrations";
import { Button } from "@/components/ui/Button";
import { AlertTriangle, CheckCircle, Sparkles, UploadCloud } from "@/components/ui/icons";
import { useAuthStore } from "@/stores/auth";
import { getErrorMessage } from "@/utils/errors";

const MAX_FILES = 10;
const DESTINATIONS: { key: PlanDestination; label: string }[] = [
  { key: "products", label: "Product catalog" },
  { key: "inventory", label: "Inventory levels" },
  { key: "sales", label: "Dated sales" },
  { key: "period_sales", label: "Period sales totals" },
];
// Mirrors backend import_plan.DESTINATION_FIELDS (style/cogs are planner-only fields).
const FIELDS: Record<PlanDestination, string[]> = {
  products: ["sku", "name", "brand", "category", "description", "gtin", "price", "size", "color", "currency"],
  inventory: ["sku", "available", "reserved", "inbound", "warehouse"],
  sales: ["sku", "name", "quantity", "timestamp", "price", "revenue", "discount", "channel", "region",
    "order_id", "line_id", "in_stock", "stockout", "returns", "warehouse", "currency"],
  period_sales: ["sku", "quantity", "revenue", "cogs", "warehouse"],
};
const SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "FREE"];
const UNUSABLE: Record<string, string> = {
  no_item_column: "No column identifies an item (no SKU or item code). This looks like a summary report — "
    + "ask for the item-wise version of this report: one row per item with its date, item code and quantity.",
  no_quantity_or_catalogue: "No stock, sales quantity or catalogue column was found.",
  summary_only: "Only totals were found, no item rows.",
};
const EXCLUSION: Record<string, string> = {
  summary_row: "total row", no_item: "no item code", repeated_header: "repeated header", subtotal: "subtotal",
};

type Card = {
  file: File;
  plan: FilePlan;
  decision: PlanDecision;
  evaluation: PlanEvaluation;
  stale: boolean;
  busy: boolean;
  error: string | null;
  result: PlanConfirmResult | null;
};

function fieldsFor(destinations: PlanDestination[]): string[] {
  const fields = destinations.flatMap((d) => FIELDS[d]);
  return [...new Set([...fields, ...(destinations.length ? ["style"] : [])])];
}

function ready(card: Card) {
  return card.decision.destinations.length > 0 && !card.result && !card.evaluation.problems?.length
    && Object.values(card.evaluation.missing).every((m) => !m?.length);
}

function summary(result: PlanConfirmResult): string {
  const d = result.destinations;
  const parts = [
    d.products && `${d.products.rows_imported ?? 0} catalog items`,
    d.inventory && `${d.inventory.inventory_rows ?? 0} stock positions`,
    d.sales && `${d.sales.sales_rows ?? 0} sales rows`,
    d.period_sales && `${d.period_sales.period_rows ?? 0} period totals`,
  ].filter(Boolean);
  return `Imported ${parts.join(", ")}`;
}

export function SmartImport({ onImported }: { onImported?: () => void }) {
  const role = useAuthStore((s) => s.role);
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [failed, setFailed] = useState<{ filename: string; error: string }[]>([]);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canImport = role !== "viewer";

  async function plan(list: File[]) {
    if (!list.length) return;
    if (list.length > MAX_FILES) { setError(`Choose at most ${MAX_FILES} files at once.`); return; }
    setPlanning(true); setError(null); setCards([]); setFailed([]);
    try {
      const { files } = await integrationsApi.planImport(list);
      setCards(files.filter((s): s is FilePlan => !("error" in s)).map((plan) => ({
        file: list[plan.file_index], plan, decision: plan.decision, evaluation: plan, stale: false,
        busy: false, error: null, result: null,
      })));
      setFailed(files.filter((s): s is Extract<FilePlanSlot, { error: string }> => "error" in s));
    } catch (e) {
      setError(getErrorMessage(e, "Could not analyse these files."));
    } finally {
      setPlanning(false);
    }
  }

  function patch(index: number, change: Partial<Card>) {
    setCards((old) => old.map((c, i) => (i === index ? { ...c, ...change } : c)));
  }

  function edit(index: number, change: Partial<PlanDecision>) {
    setCards((old) => old.map((c, i) => (i === index ? { ...c, decision: { ...c.decision, ...change }, stale: true } : c)));
  }

  async function refresh(index: number) {
    const card = cards[index];
    patch(index, { busy: true, error: null });
    try {
      const next = await integrationsApi.previewPlan(card.file, card.plan.plan_token, card.decision);
      patch(index, { evaluation: next, decision: next.decision, stale: false, busy: false });
    } catch (e) {
      patch(index, { busy: false, error: getErrorMessage(e, "Preview failed.") });
    }
  }

  async function confirm(index: number, card: Card = cards[index]) {
    patch(index, { busy: true, error: null });
    try {
      const result = await integrationsApi.confirmPlan(card.file, card.plan.plan_token, card.decision);
      patch(index, { busy: false, result });
      toast.success(`${card.plan.filename}: ${summary(result)}`);
      onImported?.();
    } catch (e) {
      patch(index, { busy: false, error: getErrorMessage(e, "Import failed. Nothing from this file was saved.") });
    }
  }

  async function confirmAll() {
    for (const [index, card] of cards.entries()) if (ready(card)) await confirm(index, card);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    void plan(Array.from(e.dataTransfer.files ?? []));
  }

  return <div className="space-y-4 text-sm">
    <label htmlFor={inputId} onDragOver={(e) => e.preventDefault()} onDrop={onDrop}
      className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 py-6 text-center">
      <UploadCloud size={22} className="text-accent" aria-hidden="true" />
      <span className="font-medium text-content">Drop up to {MAX_FILES} report files, or click to browse</span>
      <span className="text-xs text-content-subtle">CSV or Excel · up to 10 MB each · each file is planned on its own</span>
      <input id={inputId} ref={input} type="file" multiple accept=".csv,.tsv,.xlsx,.xlsm" className="sr-only"
        disabled={planning} onChange={(e) => { void plan(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
    </label>
    {planning && <p role="status">Reading files and drafting a plan for each…</p>}
    {error && <p role="alert" className="rounded-xl border border-line p-3">{error}</p>}
    {failed.map((f) => <section key={f.filename} aria-label={f.filename} className="rounded-xl border border-line p-3">
      <h4 className="font-medium">{f.filename}</h4>
      <p className="text-xs text-content-muted">{f.error}</p>
    </section>)}
    {cards.map((card, index) => <PlanCard key={card.plan.file_index} card={card} canImport={canImport}
      onEdit={(c) => edit(index, c)} onRefresh={() => void refresh(index)} onConfirm={() => void confirm(index)} />)}
    {cards.filter(ready).length > 1 && canImport &&
      <Button size="sm" onClick={() => void confirmAll()}>Import all ready files ({cards.filter(ready).length})</Button>}
  </div>;
}

function PlanCard({ card, canImport, onEdit, onRefresh, onConfirm }: {
  card: Card; canImport: boolean; onEdit: (c: Partial<PlanDecision>) => void; onRefresh: () => void; onConfirm: () => void;
}) {
  const { plan, decision, evaluation } = card;
  const { preview } = evaluation;
  const unusable = decision.destinations.length === 0 && plan.unusable_reason;
  const [sizeSearch, setSizeSearch] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const needsReview = (code: PlanEvaluation["size_codes"][number]) =>
    !Object.hasOwn(decision.size_map, code.code) && !code.suggestion;
  const reviewCount = evaluation.size_codes.filter(needsReview).length;
  const visibleSizes = evaluation.size_codes.filter((c) =>
    (!reviewOnly || needsReview(c)) && `${c.code} ${c.meaning ?? ""} ${c.suggestion ?? ""}`.toLowerCase().includes(sizeSearch.trim().toLowerCase()));
  const missing = Object.entries(evaluation.missing).filter(([, m]) => m?.length);

  return <section aria-label={plan.filename} className="space-y-3 rounded-xl border border-line bg-surface-2 p-3">
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h4 className="font-medium text-content">{plan.filename}</h4>
        <p className="text-xs text-content-subtle">{plan.table.sheet} · header row {plan.table.header_start} · {plan.table.rows_total} rows</p>
      </div>
      <span className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs">
        <Sparkles size={12} aria-hidden="true" />{plan.plan_source === "ai" ? "AI-assisted plan" : "Rules plan"}
      </span>
    </header>
    {plan.plan_source === "rules" && !["disabled", "success"].includes(plan.ai_state) &&
      <p className="text-xs">AI suggestions unavailable ({plan.ai_state}); this plan uses header rules only.</p>}

    {unusable ? <p className="flex gap-2 text-xs"><AlertTriangle size={14} aria-hidden="true" className="mt-0.5 shrink-0" />
      {UNUSABLE[plan.unusable_reason!] ?? plan.unusable_reason}</p> : <>
      <fieldset className="flex flex-wrap gap-3 text-xs"><legend className="mb-1 font-medium">Import into</legend>
        {DESTINATIONS.map((d) => <label key={d.key} className="flex items-center gap-1">
          <input type="checkbox" checked={decision.destinations.includes(d.key)} onChange={(e) => onEdit({
            destinations: e.target.checked ? [...decision.destinations, d.key] : decision.destinations.filter((x) => x !== d.key),
          })} />{d.label}</label>)}
      </fieldset>

      <fieldset className="flex flex-wrap gap-3 text-xs"><legend className="mb-1 font-medium">Reshape</legend>
        <label className="flex items-center gap-1"><input type="checkbox" checked={decision.transforms.parse_variant}
          onChange={(e) => onEdit({ transforms: { ...decision.transforms, parse_variant: e.target.checked } })} />
          Read colour and size from description</label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={decision.transforms.group_pieces}
          onChange={(e) => onEdit({ transforms: { ...decision.transforms, group_pieces: e.target.checked } })} />
          Group pieces into style + colour + size SKUs</label>
      </fieldset>

      {decision.destinations.includes("period_sales") && <fieldset className="grid gap-2 text-xs sm:grid-cols-2">
        <legend className="mb-1 font-medium">Period these totals cover</legend>
        <label className="flex flex-col gap-1">From<input className="input" type="date" value={decision.period?.start ?? ""}
          onChange={(e) => onEdit({ period: { start: e.target.value, end: decision.period?.end ?? e.target.value } })} /></label>
        <label className="flex flex-col gap-1">To<input className="input" type="date" value={decision.period?.end ?? ""}
          onChange={(e) => onEdit({ period: { start: decision.period?.start ?? e.target.value, end: e.target.value } })} /></label>
      </fieldset>}

      <details className="text-xs"><summary>Column mapping</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">{fieldsFor(decision.destinations).map((field) =>
          <label key={field} className="flex flex-col gap-1">{field.replaceAll("_", " ")}
            <select className="input" aria-label={`${plan.filename}: ${field}`} value={decision.mapping[field] ?? ""}
              onChange={(e) => onEdit({ mapping: { ...decision.mapping, [field]: e.target.value } })}>
              <option value="">Skip / not supplied</option>
              {plan.columns.map((c) => <option key={c.id} value={c.id}>{c.label}{plan.provenance[c.id] === "ai" ? " (AI)" : ""}</option>)}
            </select></label>)}</div>
      </details>

      {evaluation.size_codes.length > 0 && <details className="rounded-xl border border-line-strong bg-surface p-4 text-xs" open>
        <summary className="cursor-pointer font-medium text-content">Size recognition · {evaluation.size_codes.length} codes · {reviewCount} need review</summary>
        <p className="mt-2 text-content-muted">Recognised letter sizes are applied automatically. Original codes stay in the SKU. Numeric sizes and ranges are identified below; choose a letter size only if appropriate.</p>
        <div className="my-4 flex flex-wrap items-end gap-4">
          <label className="flex min-w-0 flex-1 flex-col gap-1">Search size codes
            <input type="search" className="input w-full" value={sizeSearch} placeholder="Code, meaning or detected size"
              onChange={(e) => setSizeSearch(e.target.value)} /></label>
          <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={reviewOnly}
            onChange={(e) => setReviewOnly(e.target.checked)} />Needs review only</label>
          <span role="status" className="pb-3 text-content-subtle">Showing {visibleSizes.length} of {evaluation.size_codes.length}</span>
        </div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-4">{visibleSizes.map((c) => {
          const overridden = Object.hasOwn(decision.size_map, c.code);
          return <div key={c.code} className="min-w-0 rounded-xl border border-line-strong bg-surface-2 p-4">
            <dl className="mb-3 flex items-start justify-between gap-4">
              <div className="min-w-0"><dt className="text-content-subtle">Original code</dt>
                <dd className="mt-1 break-words font-mono text-base font-semibold text-content">{c.code}</dd></div>
              <div className="shrink-0 text-right"><dt className="text-content-subtle">Rows using it</dt>
                <dd className="mt-1 font-mono text-base text-content">{c.count.toLocaleString()}</dd></div>
            </dl>
            <p className="mb-3 min-h-8 text-content-muted">{c.meaning ?? (c.suggestion ? `Letter size: ${c.suggestion}` : "Source-specific code — review required")}</p>
            <label className="flex flex-col gap-1">Detected size / override
              <select className="input w-full" aria-label={`Size for code ${c.code}`} value={decision.size_map[c.code] ?? c.suggestion ?? ""}
                onChange={(e) => onEdit({ size_map: { ...decision.size_map, [c.code]: e.target.value } })}>
                <option value="">Leave blank</option>{SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <div className="mt-2 flex min-h-7 items-center justify-between gap-2">
              <span className="text-content-subtle">{overridden ? (decision.size_map[c.code] ? "Your selection" : "Reviewed · left blank") : c.suggestion ? "Automatically recognised" : "Needs review"}</span>
              {overridden ? <button type="button" className="underline" onClick={() => {
                const next = { ...decision.size_map }; delete next[c.code]; onEdit({ size_map: next });
              }}>Reset</button> : !c.suggestion && <button type="button" className="underline"
                onClick={() => onEdit({ size_map: { ...decision.size_map, [c.code]: "" } })}>Keep blank</button>}
            </div>
          </div>;
        })}</div>
        {visibleSizes.length === 0 && <p className="py-6 text-center text-content-muted">No size codes match these filters.</p>}
      </details>}

      <p className={clsx("text-xs", card.stale && "text-content-subtle")}>
        {preview.source_rows} rows → {preview.items} SKUs in {preview.output_rows} rows
        {preview.locations ? ` across ${preview.locations} locations` : ""} · {preview.excluded_rows} excluded
        {preview.conflicts ? ` · ${preview.conflicts} SKUs had pieces with differing price or details (most common kept)` : ""}
        {card.stale ? " · preview out of date" : ""}
      </p>
      {preview.after.length > 0 && <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <caption className="text-left text-content-subtle">After (first rows)</caption>
        <thead><tr>{Object.keys(preview.after[0]).map((f) => <th key={f} className="p-1">{f}</th>)}</tr></thead>
        <tbody>{preview.after.map((row, i) => <tr key={i}>{Object.keys(preview.after[0]).map((f) =>
          <td key={f} className="p-1">{row[f] == null ? "—" : String(row[f])}</td>)}</tr>)}</tbody>
      </table></div>}
      {evaluation.exclusions.length > 0 && <details className="text-xs"><summary>{preview.excluded_rows} excluded rows</summary>
        <ul>{evaluation.exclusions.map((e) => <li key={e.row}>Row {e.row}: {EXCLUSION[e.reason] ?? e.reason}</li>)}</ul></details>}
      {missing.length > 0 && <p role="alert" className="text-xs">Map required fields: {missing.map(([d, m]) =>
        `${d.replace("_", " ")} needs ${m!.map((f) => (f === "period" ? "a period" : f)).join(", ")}`).join("; ")}</p>}
      {card.evaluation.problems?.map((problem) => <p key={problem} role="alert" className="text-xs">{problem}</p>)}
      {card.error && <p role="alert" className="rounded-lg border border-line p-2 text-xs">{card.error}</p>}
      {card.result ? <p role="status" className="flex items-center gap-1 text-xs"><CheckCircle size={14} aria-hidden="true" />{summary(card.result)}</p>
        : <div className="sticky bottom-0 z-10 flex flex-wrap gap-2 border-t border-line bg-surface-2 py-3">
          <Button size="sm" variant="ghost" onClick={onRefresh} disabled={card.busy}>Update preview</Button>
          <Button size="sm" variant="secondary" onClick={onConfirm} loading={card.busy}
            disabled={!canImport || card.busy || !ready(card)}>Import this file</Button>
        </div>}
    </>}
  </section>;
}
