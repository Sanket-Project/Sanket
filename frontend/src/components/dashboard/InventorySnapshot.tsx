import { useState } from "react";
import { Link } from "react-router-dom";
import type { SkuCoverage } from "@/api/inventory";
import type { SkuConfidence } from "@/api/forecasts";
import { Boxes, ArrowRight } from "@/components/ui/icons";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

const statusLabel = { critical: "Critical", low: "Low cover", excess: "Overstock", healthy: "Enough stock", unknown: "Needs data" };

export function InventorySnapshot({ skus, confidence = [], unavailable = false }: {
  skus?: SkuCoverage[]; confidence?: SkuConfidence[]; unavailable?: boolean;
}) {
  const [view, setView] = useState<"risk" | "excess" | "all">("risk");
  const rows = (skus ?? []).filter(row => view === "all" || (view === "excess" ? row.sku_wide.status === "excess" : ["critical", "low"].includes(row.sku_wide.status)))
    .sort((a, b) => (a.sku_wide.cover_days ?? Infinity) - (b.sku_wide.cover_days ?? Infinity)).slice(0, 5);
  return <Card title={<span className="inline-flex items-center gap-2"><Boxes size={17} />Inventory snapshot</span>} padding="sm">
    <div aria-label="Inventory snapshot views" className="mb-3 flex flex-wrap gap-1 border-b border-line pb-2">
      {([['risk', 'At risk'], ['excess', 'Overstock'], ['all', 'All stock']] as const).map(([id, label]) => <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)} className={`rounded-lg px-2.5 py-1.5 text-xs font-medium ${view === id ? "bg-accent-soft text-accent" : "text-content-muted hover:bg-surface-2"}`}>{label}</button>)}
    </div>
    {unavailable ? <p role="status" className="py-3 text-sm text-content-muted">Stock coverage unavailable. Open inventory to retry.</p>
      : !skus ? <p role="status" className="py-3 text-sm text-content-muted">Checking stock coverage…</p>
      : !rows.length ? <p className="py-3 text-sm text-content-muted">{view === "risk" ? "No at-risk stock in the current coverage report." : "No stock matches this view."}</p>
      : <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="sr-only">Recorded stock coverage and data confidence</caption>
        <thead className="text-content-muted"><tr><th scope="col" className="pb-2 font-medium">SKU</th><th scope="col" className="px-2 pb-2 font-medium">Cover</th><th scope="col" className="pb-2 font-medium">Stock risk</th><th scope="col" className="pb-2 pl-2 text-right font-medium">Confidence</th></tr></thead>
        <tbody>{rows.map(row => { const score = confidence.find(item => item.sku_id === row.sku_id); const status = row.sku_wide.status; return <tr key={row.sku_id} className="border-t border-line">
          <td className="max-w-28 py-3 pr-2"><Link to={`/workspace/skus/${encodeURIComponent(row.sku_id)}`} className="break-all font-medium text-content hover:text-accent">{row.sku_code}</Link></td>
          <td className="px-2 font-mono text-content-muted">{row.sku_wide.cover_days == null ? "Unknown" : `${Math.round(row.sku_wide.cover_days)}d`}</td>
          <td><Badge variant={status === "critical" ? "danger" : status === "low" ? "warning" : status === "healthy" ? "success" : "default"}>{statusLabel[status]}</Badge></td>
          <td className="pl-2 text-right font-mono text-content-muted" title="Data readiness score; not measured forecast accuracy">{score ? `${score.confidence}/100` : "Not scored"}</td>
        </tr>; })}</tbody>
      </table></div>}
    <Link to="/workspace/inventory" className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-accent">Review inventory <ArrowRight size={13} /></Link>
  </Card>;
}
