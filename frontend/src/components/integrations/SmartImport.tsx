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
  return card.decision.destinations.length > 0 && !card.result
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
  const unknownSizes = evaluation.size_codes.filter((c) => !c.suggestion);
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

      {unknownSizes.length > 0 && <details className="text-xs" open><summary>{unknownSizes.length} size codes need a size</summary>
        <p className="my-1 text-content-muted">These codes are not standard sizes. Pick one, or leave blank — the code stays part of the SKU either way.</p>
        <div className="grid gap-1 sm:grid-cols-3">{unknownSizes.slice(0, 60).map((c) => <label key={c.code} className="flex items-center gap-2">
          <span className="w-20 font-mono">{c.code}</span><span className="w-12 text-content-subtle">{c.count}</span>
          <select className="input" aria-label={`Size for code ${c.code}`} value={decision.size_map[c.code] ?? ""}
            onChange={(e) => onEdit({ size_map: { ...decision.size_map, [c.code]: e.target.value } })}>
            <option value="">Leave blank</option>{SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></label>)}</div>
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
      {card.error && <p role="alert" className="rounded-lg border border-line p-2 text-xs">{card.error}</p>}
      {card.result ? <p role="status" className="flex items-center gap-1 text-xs"><CheckCircle size={14} aria-hidden="true" />{summary(card.result)}</p>
        : <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={onRefresh} disabled={card.busy}>Update preview</Button>
          <Button size="sm" variant="secondary" onClick={onConfirm} loading={card.busy}
            disabled={!canImport || card.busy || !ready(card)}>Import this file</Button>
        </div>}
    </>}
  </section>;
}
