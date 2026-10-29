import { useEffect, useId, useRef, useState } from "react";
import toast from "react-hot-toast";
import { integrationsApi, type ImportAnalysis, type TableSelection, type UploadOptions, type UploadResult, type V2Preview } from "@/api/integrations";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { useAuthStore } from "@/stores/auth";
import { getErrorMessage } from "@/utils/errors";
import { describeUploadResult } from "@/utils/uploadSummary";

type Kind = "sales" | "inventory" | "products";
const LEGACY_FIELDS: Record<Kind, string[]> = {
  sales: ["sku", "name", "quantity", "timestamp", "price", "revenue", "discount", "channel", "region", "order_id", "line_id", "warehouse", "returns", "in_stock", "stockout", "currency"],
  inventory: ["sku", "available", "reserved", "inbound", "warehouse"],
  products: ["sku", "name", "brand", "category", "description", "gtin", "price", "size", "color", "currency"],
};

function mappingError(kind: Kind, mapping: Record<string, string>): string | null {
  const active = Object.entries(mapping).filter(([, v]) => v);
  if (new Set(active.map(([, v]) => v)).size !== active.length) return "A column cannot map to multiple fields.";
  if (!mapping.sku && (!mapping.name || kind === "inventory")) return "Map SKU or Product Name before importing.";
  if (kind === "sales" && (!mapping.quantity || !mapping.timestamp)) return "Map quantity and timestamp before importing.";
  if (kind === "inventory" && !mapping.available) return "Map available stock before importing.";
  return null;
}

export function ImportUploader({ kind, onImported, mode = "onboarding" }: {
  kind: Kind; onImported?: (result: UploadResult) => void; mode?: "onboarding" | "integrations";
}) {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const role = useAuthStore((s) => s.role);
  const identityId = useId();
  const version = useRef(0);
  const headerOverrides = useRef<Record<string, [number, number]>>();
  const activeScope = useRef(scope);
  const activeKind = useRef(kind);
  activeScope.current = scope;
  activeKind.current = kind;
  const sending = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [v2Preview, setV2Preview] = useState<V2Preview | null>(null);
  const [v2Result, setV2Result] = useState<Record<string, unknown> | null>(null);
  const [selections, setSelections] = useState<TableSelection[]>([]);
  const [legacyMapping, setLegacyMapping] = useState<Record<string, string>>({});
  const [identity, setIdentity] = useState<"transaction" | "period">("transaction");
  const [currency, setCurrency] = useState("");
  const [remember, setRemember] = useState(false);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [manualSheet, setManualSheet] = useState("CSV");
  const [headerStart, setHeaderStart] = useState(1);
  const [headerEnd, setHeaderEnd] = useState(1);

  useEffect(() => {
    version.current += 1;
    setFile(null); setAnalysis(null); setV2Preview(null); setV2Result(null); setSelections([]); setError(null); setResult(null); setPending(false);
    setIdentity("transaction"); setCurrency(""); setRemember(false); setLegacyMapping({});
    setManualSheet("CSV"); setHeaderStart(1); setHeaderEnd(1); headerOverrides.current = undefined;
    return () => { version.current += 1; };
  }, [scope, kind]);

  async function analyze(selected: File | null, overrides?: Record<string, [number, number]>, targetTable?: string) {
    const revision = ++version.current;
    const effectiveOverrides = overrides || (targetTable ? headerOverrides.current : undefined);
    if (!targetTable) headerOverrides.current = overrides;
    setFile(selected); setAnalysis(null); setV2Preview(null); setV2Result(null); setSelections([]); setError(null); setResult(null); setPending(!!selected);
    if (!selected) return;
    try {
      if (/\.(csv|tsv)$/i.test(selected.name)) {
        const probe = selected.slice(0, 512);
        const prefix = typeof probe.text === "function" ? await probe.text() : "";
        if (prefix.includes("retail_v2.0.") && typeof integrationsApi.v2Preview === "function") {
          const preview = await integrationsApi.v2Preview(selected);
          if (revision !== version.current || activeScope.current !== scope || activeKind.current !== kind) return;
          setV2Preview(preview);
          return;
        }
      }
      const data = await integrationsApi.analyze(selected, kind, effectiveOverrides, targetTable);
      if (revision !== version.current || activeScope.current !== scope || activeKind.current !== kind) return;
      setAnalysis(data);
      setLegacyMapping(data.suggested_mapping || {});
      if (data.tables?.length) {
        const top = data.tables[0];
        if (targetTable) {
          setSelections(selections.map((s) => s.id === targetTable ? { ...s, mapping: { ...data.tables!.find((t) => t.id === targetTable)!.mapping } } : s));
        } else {
          setSelections([{ id: top.id, mapping: { ...top.mapping }, include_review_rows: [], exclude_rows: [],
            ...(top.saved_options?.date_order ? { date_order: top.saved_options.date_order } : {}) }]);
        }
        if (top.saved_options?.identity) setIdentity(top.saved_options.identity);
        if (top.saved_options?.currency) setCurrency(top.saved_options.currency);
        setManualSheet(top.sheet); setHeaderStart(top.header_start); setHeaderEnd(top.header_end);
      }
    } catch (e) {
      if (revision === version.current && activeScope.current === scope) setError(getErrorMessage(e, "File analysis failed. Select the sheet and header rows to retry."));
    } finally {
      if (revision === version.current && activeScope.current === scope) setPending(false);
    }
  }

  const validation = analysis?.tables
    ? !selections.length ? "Select at least one table." : selections.map((selection) => {
      const table = analysis.tables!.find((t) => t.id === selection.id)!;
      return mappingError(kind, selection.mapping)
        || (kind !== "products" && ((table.new_sku_count || 0) > 0 || selection.mapping.sku !== table.mapping.sku || selection.mapping.name !== table.mapping.name) && !selection.allow_new_skus ? "Review new SKU creation before importing." : null)
        || (kind === "sales" && (table.date_review_counts?.[selection.mapping.timestamp] || 0) > 0 && !selection.date_order ? "Select the date order before importing ambiguous dates." : null)
        || (table.review_rows.some((n) => !selection.include_review_rows.includes(n) && !selection.exclude_rows.includes(n)) ? "Review ambiguous rows before importing." : null);
    }).find(Boolean)
    : analysis ? mappingError(kind, legacyMapping) : null;
  const problem = error || validation || (v2Preview && !v2Preview.can_confirm ? "Resolve all V2 preview errors before confirming." : null);

  function update(id: string, patch: Partial<TableSelection>) {
    setSelections((previous) => previous.map((s) => s.id === id ? { ...s, ...patch, ...(patch.mapping ? { allow_new_skus: false } : {}) } : s));
    setResult(null);
  }

  async function run() {
    if (!file || (!analysis && !v2Preview) || problem || pending || sending.current || role === "viewer") return;
    sending.current = true; setBusy(true); setError(null);
    const revision = version.current;
    if (v2Preview) {
      try {
        const confirmed = await integrationsApi.v2Confirm(file, v2Preview.preview_token);
        if (revision !== version.current || activeScope.current !== scope || activeKind.current !== kind) return;
        setV2Result(confirmed);
        toast.success("V2 import confirmed");
        const inserted = Number(confirmed.inserted ?? 0);
        const skipped = Number(confirmed.skipped ?? 0);
        onImported?.({
          provider: "retail_v2", kind: v2Preview.schema.split(".").at(-1) || kind,
          rows_total: Number(confirmed.rows ?? v2Preview.row_count),
          rows_imported: inserted, rows_skipped: skipped,
          products_created: 0, skus_created: 0,
          inventory_rows: v2Preview.schema.endsWith(".inventory") ? inserted : 0,
          sales_rows: v2Preview.schema.endsWith(".sales") ? inserted + skipped : 0,
          rows_inserted: inserted, rows_unchanged: skipped, rows_updated: 0,
          identity_mode: "transaction", warnings: [], errors: [],
        });
        return;
      } catch (e) {
        if (revision === version.current) setError(getErrorMessage(e, "V2 import failed. No records were posted."));
        return;
      } finally {
        sending.current = false; setBusy(false);
      }
    }
    if (!analysis) { sending.current = false; setBusy(false); return; }
    const options: UploadOptions = kind === "sales" ? { identity } : {};
    if (mode === "integrations" || currency) options.currency = currency || undefined;
    if (analysis.analysis_token) Object.assign(options, { analysisToken: analysis.analysis_token, tableSelections: selections, rememberMapping: remember });
    try {
      const uploaded = await integrationsApi.upload(file, kind, selections[0]?.mapping || legacyMapping, options);
      if (revision !== version.current || activeScope.current !== scope || activeKind.current !== kind) return;
      const accepted = kind === "sales" ? uploaded.rows_inserted + uploaded.rows_updated + uploaded.rows_unchanged
        : kind === "products" ? uploaded.skus_created : uploaded.inventory_rows;
      if (accepted === 0) { setError(uploaded.errors?.[0] || "No rows were accepted. Review the mapping and file."); return; }
      setResult(uploaded);
      toast.success(describeUploadResult(uploaded));
      onImported?.(uploaded);
    } catch (e) {
      if (revision === version.current) setError(getErrorMessage(e, "Import failed. No saved format was trusted."));
    } finally { sending.current = false; setBusy(false); }
  }

  return <div className="space-y-3 text-sm">
    <FileDropzone file={file} onFile={(selected) => void analyze(selected)} accept=".csv,.tsv,.xlsx,.xlsm" hint="CSV or Excel · up to 10 MB" disabled={busy} />
    {pending && <p role="status">Analyzing file layout…</p>}
    {v2Preview && <section className="space-y-2 rounded-xl border border-line bg-surface-2 p-3" aria-label="V2 preview">
      <p className="font-medium">{v2Preview.schema} · {v2Preview.row_count} rows</p>
      {v2Preview.errors.length > 0
        ? <ul role="alert" className="space-y-1 text-xs">{v2Preview.errors.map((item) => <li key={`${item.row}-${item.code}`}>Row {item.row}: {item.message}</li>)}</ul>
        : <p className="text-xs">Tenant references and financial controls passed preview.</p>}
    </section>}
    {file && !pending && <details className="rounded-xl border border-line p-3 text-xs">
      <summary>Choose sheet and header rows manually</summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <label>Sheet<input className="input" value={manualSheet} onChange={(e) => setManualSheet(e.target.value)} /></label>
        <label>First header row<input className="input" type="number" min={1} value={headerStart} onChange={(e) => setHeaderStart(Number(e.target.value))} /></label>
        <label>Last header row<input className="input" type="number" min={headerStart} value={headerEnd} onChange={(e) => setHeaderEnd(Number(e.target.value))} /></label>
      </div>
      <Button size="sm" variant="secondary" onClick={() => void analyze(file, { [manualSheet]: [headerStart, headerEnd] })}>Analyze selected rows</Button>
    </details>}
    {analysis?.tables?.map((table) => {
      const selected = selections.find((s) => s.id === table.id);
      return <section className="space-y-3 rounded-xl border border-line bg-surface-2 p-3" key={table.id}>
        <label className="flex items-center gap-2 font-medium"><input type="checkbox" checked={!!selected} onChange={(e) => setSelections((old) => e.target.checked ? [...old, { id: table.id, mapping: { ...table.mapping }, include_review_rows: [], exclude_rows: [] }] : old.filter((s) => s.id !== table.id))} />
          {table.sheet} · header {table.header_start}{table.header_end !== table.header_start ? `–${table.header_end}` : ""} · {table.rows_total} detail rows
        </label>
        {table.mapping_source === "saved" && <p className="text-xs">Saved workspace format applied. Review and press Import.</p>}
        {table.ai_state !== "success" && table.ai_state !== "disabled" && <p role="status" className="text-xs">AI suggestions unavailable. Manual mapping is available.</p>}
        {selected && <>
          <Button size="sm" variant="ghost" onClick={() => void analyze(file, undefined, table.id)}>Suggest mapping for this table</Button>
          {kind !== "products" && ((table.new_sku_count || 0) > 0 || selected.mapping.sku !== table.mapping.sku || selected.mapping.name !== table.mapping.name) && <fieldset className="space-y-2 rounded-xl border border-line p-3 text-xs">
            <legend>New SKU review</legend>
            <p>{table.new_sku_count || 0} new SKU codes detected in the suggested mapping. Check for spelling differences before creating items.</p>
            {!!table.new_skus?.length && <details open><summary>New SKU codes{table.new_sku_count && table.new_sku_count > table.new_skus.length ? ` (first ${table.new_skus.length})` : ""}</summary><ul className="max-h-40 overflow-y-auto">{table.new_skus.map((code) => <li key={code}>{code}</li>)}</ul></details>}
            {(selected.mapping.sku !== table.mapping.sku || selected.mapping.name !== table.mapping.name) && <p>The SKU mapping changed. Review the selected source column; new codes are checked again on import.</p>}
            <label className="flex items-center gap-2"><input type="checkbox" checked={!!selected.allow_new_skus} onChange={(e) => update(table.id, { allow_new_skus: e.target.checked })} />Create new SKUs from the selected mapping</label>
          </fieldset>}
          {kind === "sales" && <div className="space-y-2 text-xs"><label>Date interpretation<select className="input" aria-label={`${table.sheet}: date order`} value={selected.date_order || ""} onChange={(e) => update(table.id, { date_order: (e.target.value || undefined) as TableSelection["date_order"] })}><option value="">Use unambiguous source dates</option><option value="dmy">Day / month / year</option><option value="mdy">Month / day / year</option></select></label>
            {(table.date_reviews?.[selected.mapping.timestamp] || []).map((date) => <p key={date.row}>Row {date.row}: {date.value} → day/month: {date.dmy}; month/day: {date.mdy}</p>)}
          </div>}
          <div className="grid gap-2 sm:grid-cols-2">{(analysis.fields || LEGACY_FIELDS[kind]).map((field) => <label className="flex flex-col gap-1 text-xs" key={field}>
            {field.replaceAll("_", " ")}
            <select className="input" aria-label={`${table.sheet}: ${field}`} value={selected.mapping[field] || ""} onChange={(e) => update(table.id, { mapping: { ...selected.mapping, [field]: e.target.value } })}>
              <option value="">Skip / not supplied</option>{table.columns.map((c) => <option key={c.id} value={c.id}>{c.display_label}</option>)}
            </select>
          </label>)}</div>
          <ul className="space-y-1 text-xs">{table.columns.map((c) => <li key={c.id}>{c.display_label}: {table.provenance[c.id] === "ai" ? `AI-generated · Model estimate: ${table.confidence[c.id] || "unknown"}` : table.provenance[c.id] === "saved" ? "Human-confirmed format" : table.provenance[c.id] === "alias" ? "Header match" : "Unmapped / unsupported"}</li>)}</ul>
          {table.sample_rows?.length > 0 && <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="text-left">Source preview</caption><thead><tr>{table.columns.map((c) => <th className="p-1" key={c.id}>{c.display_label}</th>)}</tr></thead><tbody>{table.sample_rows.map((row, i) => <tr key={i}>{table.columns.map((c) => <td className="p-1" key={c.id}>{row[c.id] == null ? "Missing" : String(row[c.id])}</td>)}</tr>)}</tbody></table></div>}
          {table.exclusions.length > 0 && <details><summary>{table.exclusions.length} excluded summary/header rows</summary><ul>{table.exclusions.map((r) => <li key={r.row}>Row {r.row}: {r.reason}</li>)}</ul></details>}
          {table.review_rows.map((row) => <label className="block text-xs" key={row}>Review row {row}<select className="input" aria-label={`Row ${row}`} value={selected.include_review_rows.includes(row) ? "include" : selected.exclude_rows.includes(row) ? "exclude" : ""} onChange={(e) => update(table.id, { include_review_rows: [...selected.include_review_rows.filter((n) => n !== row), ...(e.target.value === "include" ? [row] : [])], exclude_rows: [...selected.exclude_rows.filter((n) => n !== row), ...(e.target.value === "exclude" ? [row] : [])] })}><option value="">Choose</option><option value="include">Include as detail</option><option value="exclude">Exclude</option></select></label>)}
          {table.warning_count > 0 && <details><summary>{table.warning_count} source warnings</summary><ul>{table.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
        </>}
      </section>;
    })}
    {analysis && !analysis.tables && <div className="grid gap-2 sm:grid-cols-2">{LEGACY_FIELDS[kind].map((field) => <label key={field}>{field}<select className="input" value={legacyMapping[field] || ""} onChange={(e) => setLegacyMapping((m) => ({ ...m, [field]: e.target.value }))}><option value="">Skip</option>{analysis.headers.map((h) => <option key={h} value={h}>{h}</option>)}</select></label>)}</div>}
    {analysis && kind === "sales" && <fieldset className="space-y-2 rounded-xl border border-line p-3 text-xs"><legend>If this file is uploaded again</legend>
      <label className="block"><input type="radio" name={identityId} checked={identity === "transaction"} onChange={() => setIdentity("transaction")} /> Individual sales (identical rows are skipped)</label>
      <label className="block"><input type="radio" name={identityId} checked={identity === "period"} onChange={() => setIdentity("period")} /> {mode === "integrations" ? "Daily or weekly totals (corrections replace)" : "Weekly/daily totals (corrections replace)"}</label>
      <label className="block">Currency of prices<select className="input" value={currency} onChange={(e) => setCurrency(e.target.value)}><option value="">Workspace default</option><option value="INR">INR</option><option value="USD">USD</option></select></label>
    </fieldset>}
    {analysis?.analysis_token && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />Remember confirmed format in this workspace after a successful import</label>}
    {problem && <p role="alert" className="rounded-xl border border-line p-3 text-sm">{problem}</p>}
    {result && <section role="status" aria-label="Import result" className="space-y-1 rounded-xl border border-line p-3 text-xs">
      <p>{describeUploadResult(result)}</p>
      {!!result.source_columns_preserved && <p>{result.source_columns_preserved} row(s) include preserved source fields that SANKET does not currently analyze.</p>}
      {result.analytics_readiness && <ul>{Object.values(result.analytics_readiness).map((metric) =>
        <li key={metric.label}>{metric.label}: {metric.status === "available" ? "ready" : metric.reason || "unavailable"}</li>
      )}</ul>}
    </section>}
    {v2Result && <p role="status">V2 import complete: {String(v2Result.rows ?? 0)} rows, {String(v2Result.inserted ?? 0)} inserted, {String(v2Result.skipped ?? 0)} skipped.</p>}
    <Button size="sm" variant="secondary" onClick={() => void run()} loading={busy} disabled={(!analysis && !v2Preview) || !file || pending || busy || !!problem || role === "viewer"}>{result || v2Result ? "Re-import" : "Import"}</Button>
  </div>;
}
