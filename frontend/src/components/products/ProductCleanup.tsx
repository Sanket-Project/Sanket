import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { aiApi, type CleanupChange } from "@/api/ai";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";

export function ProductCleanup({ skus }: { skus: { id: string; sku_code: string }[] }) {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  return <Cleanup key={scope} skus={skus} />;
}

function Cleanup({ skus }: { skus: { id: string; sku_code: string }[] }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [changes, setChanges] = useState<CleanupChange[]>([]);
  const client = useQueryClient();
  const suggest = useMutation({ mutationFn: () => aiApi.cleanup(selected), onSuccess: (data) => {
    setChanges(data.suggestions.map((s) => ({ sku_id: s.product_id, field: s.field, value: s.value,
      revision: data.products.find((p) => p.id === s.product_id)?.revision || "" })));
  } });
  const preview = useMutation({ mutationFn: () => aiApi.applyCleanup(changes, false) });
  const apply = useMutation({ mutationFn: () => aiApi.applyCleanup(changes, true), onSuccess: () => {
    setChanges([]); preview.reset(); suggest.reset(); void client.invalidateQueries();
  } });
  function edit(next: CleanupChange[]) { setChanges(next); preview.reset(); }
  return <details className="rounded-2xl border border-line bg-surface p-4 text-sm">
    <summary className="cursor-pointer font-medium">Review product cleanup</summary>
    <p className="my-3 text-content-subtle">Select up to 40 SKUs. Suggestions never merge SKUs or change prices. Category edits apply to the parent product and its variants.</p>
    <div className="grid max-h-48 gap-2 overflow-auto sm:grid-cols-3">{skus.map((sku) => <label key={sku.id} className="flex items-center gap-2"><input type="checkbox" checked={selected.includes(sku.id)} disabled={!selected.includes(sku.id) && selected.length >= 40} onChange={(e) => { setSelected((old) => e.target.checked ? [...old, sku.id] : old.filter((id) => id !== sku.id)); suggest.reset(); preview.reset(); setChanges([]); }} />{sku.sku_code}</label>)}</div>
    <Button size="sm" variant="secondary" onClick={() => { preview.reset(); suggest.mutate(); }} disabled={!selected.length || suggest.isPending}>Suggest cleanup</Button>
    {suggest.isPending && <p role="status">Preparing suggestions…</p>}
    {(suggest.isError || (suggest.data && suggest.data.state !== "success")) && <p role="status">AI cleanup unavailable. You can edit products manually.</p>}
    {suggest.data?.state === "success" && <div className="space-y-3">
      <p className="text-xs text-content-subtle">AI-generated suggestions</p>
      {suggest.data.suggestions.map((s, index) => {
        const product = suggest.data!.products.find((p) => p.id === s.product_id);
        const change = changes.find((c) => c.sku_id === s.product_id && c.field === s.field);
        const original = s.field === "category" ? product?.category : product?.attributes[s.field];
        return <div key={index} className="space-y-1 rounded-xl border border-line p-3">
          <label className="flex items-center gap-2"><input type="checkbox" checked={!!change} onChange={(e) => edit(e.target.checked ? [...changes, { sku_id: s.product_id, field: s.field, value: s.value, revision: product?.revision || "" }] : changes.filter((c) => !(c.sku_id === s.product_id && c.field === s.field)))} />{product?.name} · {s.field}</label>
          <p className="text-xs">Current: {original == null ? "Missing" : String(original)} · Evidence: {s.evidence} · Model estimate: {s.confidence}</p>
          {change && <input className="input" aria-label={`${product?.name}: ${s.field}`} value={change.value} onChange={(e) => edit(changes.map((c) => c === change ? { ...c, value: e.target.value } : c))} />}
        </div>;
      })}
      {suggest.data.duplicate_pairs.map(([a, b]) => <p key={`${a}:${b}`}>Possible duplicate — review manually: {skus.find((s) => s.id === a)?.sku_code} and {skus.find((s) => s.id === b)?.sku_code}. No merge has been performed.</p>)}
      {!suggest.data.suggestions.length && <p>No supported attribute changes were suggested.</p>}
      <Button size="sm" variant="secondary" onClick={() => preview.mutate()} disabled={!changes.length || preview.isPending}>Preview selected changes</Button>
      {preview.data && <div className="space-y-2">{preview.data.changes.map((c) => <p key={`${c.sku_id}:${c.field}`}>{c.field}: {c.before == null ? "Missing" : String(c.before)} → {c.value}</p>)}
        <Button size="sm" onClick={() => apply.mutate()} disabled={apply.isPending}>Apply reviewed changes</Button>
      </div>}
    </div>}
    {(preview.isError || apply.isError) && <p role="alert">The changes could not be applied. The record may have changed; generate a fresh preview.</p>}
    {apply.isSuccess && <p role="status">Reviewed changes saved.</p>}
  </details>;
}
