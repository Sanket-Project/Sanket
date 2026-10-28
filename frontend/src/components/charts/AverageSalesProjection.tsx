import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { periodProjectionApi } from "@/api/periodProjection";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { useAuthStore } from "@/stores/auth";
import { Card } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/Spinner";

const input = "rounded-lg border border-line bg-surface px-3 py-2 text-sm text-content focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]";
const number = (n: number | null) => n == null ? "Unavailable" : n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
const date = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function AverageSalesProjection() {
  const tenant = useAuthStore(s => s.tenantId);
  const industry = useWorkspaceIndustry();
  const [horizon, setHorizon] = useState(12);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["average-sales", tenant, industry, horizon, search, offset],
    queryFn: () => periodProjectionApi.get({ horizon_weeks: horizon, search, offset, limit: 25 }),
    retry: false,
  });
  const data = query.data;
  return <div className="space-y-5">
    <header><p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Forecasts · Report-based estimate</p>
      <h1 className="mt-2 text-3xl font-bold text-content">Average-sales projection</h1>
      <p className="mt-2 max-w-3xl text-sm text-content-muted">A constant daily rate from reported period sales. This estimate does not measure seasonal changes, recent trends, or demand hidden by stockouts.</p>
    </header>
    <div className="flex flex-wrap items-end gap-4">
      <label className="text-sm text-content">Projection horizon<select aria-label="Projection horizon" className={`${input} mt-1 block`} value={horizon} onChange={e => { setHorizon(Number(e.target.value)); setOffset(0); }}>
        {[4, 8, 12, 26, 52].map(weeks => <option key={weeks} value={weeks}>{weeks} weeks</option>)}</select></label>
      <label className="min-w-48 flex-1 text-sm text-content">Search projected SKUs<input aria-label="Search projected SKUs" type="search" value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} className={`${input} mt-1 block w-full`} placeholder="SKU code or product" /></label>
      <button className={input} onClick={() => void query.refetch()} disabled={query.isFetching}>Refresh projection</button>
    </div>
    {query.isError ? <div role="alert" className="rounded-xl border border-line p-5 text-content">Projection could not be loaded. Use Refresh projection to retry; no zero-demand result has been inferred.</div>
      : !data ? <PageLoader /> : <>
        <Card title="Coverage and assumptions">
          <p className="text-lg font-semibold text-content">{number(data.eligible_skus)} of {number(data.catalogue_skus)} catalogue SKUs have a usable reported average.</p>
          <p className="mt-2 text-sm text-content-muted">{number(data.missing_skus)} have no matching period sales; {number(data.unsupported_skus)} have unsupported, nonpositive or stale totals. These SKUs are excluded.</p>
          {data.source_periods.map(p => <p key={`${p.source}:${p.start}:${p.end}`} className="mt-3 text-sm text-content-muted">{p.source} · {date(p.start)}–{date(p.end)} · {p.days} days</p>)}
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-content-muted">{data.limitations.map(line => <li key={line}>{line}</li>)}</ul>
        </Card>
        <div className="grid gap-4 sm:grid-cols-3">
          <Card title="Projected units" description="Eligible SKUs matching the current search"><p className="text-2xl font-semibold text-content">{number(data.projected_units)}</p></Card>
          <Card title="Projection window"><p className="text-sm text-content">{date(data.projection_start)}–{date(data.projection_end)}</p></Card>
          <Card title="Method"><p className="text-sm text-content">Reported units ÷ source days × future days. Point estimate only.</p></Card>
        </div>
        <Card title="SKU estimates" description="Fractional units are planning averages. Stock cover pools locations; open store estimates for local coverage.">
          {!data.rows.length ? <p className="text-sm text-content-muted">No eligible SKUs match this selection. Missing sales are not evidence of zero demand.</p>
            : <div className="overflow-x-auto"><table className="w-full text-left text-sm text-content">
              <thead><tr className="border-b border-line text-content-muted">{["Product / SKU", "Units / week", `${horizon}-week units`, "Stock", "Est. cover days"].map((h, i) => <th key={h} scope="col" className={`px-3 py-3 font-medium ${i ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
              <tbody>{data.rows.map(row => <tr key={row.sku_id} className="border-b border-line align-top last:border-0">
                <td className="min-w-64 px-3 py-4"><p className="font-medium">{row.product_name}</p><p className="mt-1 font-mono text-xs text-content-muted">{row.sku_code}</p>
                  <p className="mt-2 text-xs text-content-muted">{number(row.reported_units)} reported units / {row.days} days</p>
                  <details className="mt-2"><summary className="cursor-pointer py-1 text-xs font-medium text-[var(--accent)]">Store estimates</summary>
                    {row.locations.map(loc => <div key={loc.location} className="mt-3 border-l-2 border-line pl-3 text-xs text-content-muted">
                      <p className="font-medium text-content">{loc.location}</p>
                      <p className="mt-1">Units / week: {number(loc.weekly_units)} · Projected units: {number(loc.projected_units)}</p>
                      <p className="mt-1">Stock: {number(loc.available_units)} · Est. cover days: {number(loc.estimated_cover_days)}</p>
                    </div>)}
                  </details>
                </td>
                {[row.weekly_units, row.projected_units, row.available_units, row.estimated_cover_days].map((v, i) => <td key={i} className="whitespace-nowrap px-3 py-4 text-right tabular-nums">{number(v)}</td>)}
              </tr>)}</tbody>
            </table></div>}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-content-muted"><span>{data.filtered_skus ? `${offset + 1}–${Math.min(offset + 25, data.filtered_skus)} of ${number(data.filtered_skus)} eligible SKUs` : "No matching eligible SKUs"}</span>
            <div className="flex gap-2"><button className={input} disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))} aria-label="Previous projection page">Previous</button><button className={input} disabled={offset + 25 >= data.filtered_skus || query.isFetching} onClick={() => setOffset(offset + 25)} aria-label="Next projection page">Next</button></div>
          </div>
        </Card>
      </>}
  </div>;
}
