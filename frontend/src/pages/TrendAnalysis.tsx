import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import clsx from "clsx";
import { ArrowRight, BarChart2, Globe, MapPin, RefreshCw, Upload } from "@/components/ui/icons";
import { trendsApi, type CompanyTrends } from "@/api/trends";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { useAuthStore } from "@/stores/auth";
import { ALL_STATES, INDIA_STATE_DISTRICTS } from "@/utils/indiaRegions";
import type { IndustryCode } from "@/types/api";

// Kept available for other evidence-focused surfaces and its regression tests.
export { TrendScoreGauge } from "@/components/charts/TrendScoreGauge";

const count = (value: number | null) => value == null ? "—" : new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(value);
const dateLabel = (value: string | null) => value ? format(parseISO(value), "d MMM yyyy") : "Not available";
const changeLabel = (value: number | null) => value == null ? "No comparison yet" : `${value > 0 ? "+" : ""}${value.toFixed(1).replace(/\.0$/, "")}%`;

function useDebounced(value: string) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => { const timer = setTimeout(() => setDebounced(value), 250); return () => clearTimeout(timer); }, [value]);
  return debounced;
}

function SalesChart({ series }: { series: CompanyTrends["sales"]["series"] }) {
  const max = Math.max(1, ...series.map((point) => point.units));
  const width = 640, height = 150, padding = 12;
  const start = Date.parse(series[0]?.date ?? ""), end = Date.parse(series.at(-1)?.date ?? "");
  const points = series.map((point) => `${padding + (Date.parse(point.date) - start) * (width - padding * 2) / Math.max(1, end - start)},${height - padding - point.units / max * (height - padding * 2)}`).join(" ");
  return <figure className="mt-6 rounded-xl bg-surface-2 p-4">
    <figcaption className="mb-3 flex items-center justify-between gap-2 text-xs text-content-muted"><span>Uploaded sales · units by date</span><span>Peak {count(max)}</span></figcaption>
    <svg role="img" aria-label={`Sales history: ${series.length} dates, from ${dateLabel(series[0]?.date ?? null)} to ${dateLabel(series.at(-1)?.date ?? null)}`} viewBox={`0 0 ${width} ${height}`} className="h-36 w-full text-accent" preserveAspectRatio="none">
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="currentColor" opacity="0.15" />
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      {series.length === 1 && <circle cx={padding} cy={height - padding - series[0].units / max * (height - padding * 2)} r="4" fill="currentColor" />}
    </svg>
    <div className="mt-2 flex justify-between text-xs text-content-subtle"><span>{dateLabel(series[0]?.date ?? null)}</span><span>{dateLabel(series.at(-1)?.date ?? null)}</span></div>
  </figure>;
}

function CompanySales({ data }: { data: CompanyTrends }) {
  const { sales, period } = data;
  return <section aria-labelledby="company-sales-title" className="rounded-[20px] border border-line bg-surface p-5 sm:p-6">
    <div className="mb-5 flex items-start gap-3"><span className="rounded-xl bg-surface-3 p-2.5 text-accent"><BarChart2 size={19} /></span>
      <div><h2 id="company-sales-title" className="font-heading text-lg font-semibold text-content">Company sales</h2><p className="mt-1 text-sm text-content-muted">Actual units from your uploaded sales history.</p></div></div>
    {sales.status !== "available" ? <div className="rounded-xl border border-dashed border-line-strong bg-surface-2 p-5">
      <p className="font-semibold text-content">{sales.status === "unmapped_geography" ? "Location mapping needed" : "No sales history for this selection"}</p>
      <p className="mt-2 text-sm leading-relaxed text-content-muted">{sales.status === "unmapped_geography" ? "Regional sales need an explicit state and district mapping on your locations. No geography is inferred from store names." : "Upload sales for your products and SKUs to compare units over time."}</p>
      {sales.status === "no_history" && <Link to="/workspace/integrations" className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-accent">Manage data imports <ArrowRight size={15} /></Link>}
    </div> : <>
      <dl className="grid grid-cols-1 gap-4 min-[480px]:grid-cols-3">
        <div className="rounded-xl bg-surface-2 p-4"><dt className="text-xs font-medium text-content-muted">Selected {period.days} days · units</dt><dd className="mt-2 font-heading text-3xl font-semibold tabular-nums text-content">{count(sales.current_units)}</dd></div>
        <div className="rounded-xl bg-surface-2 p-4"><dt className="text-xs font-medium text-content-muted">Previous {period.days} days · units</dt><dd className="mt-2 font-heading text-3xl font-semibold tabular-nums text-content">{count(sales.previous_units)}</dd></div>
        <div className="rounded-xl bg-surface-3 p-4"><dt className="text-xs font-medium text-content-muted">Change in sold units</dt><dd className="mt-2 font-heading text-2xl font-semibold tabular-nums text-content">{changeLabel(sales.change_pct)}</dd><p className="mt-1 text-xs text-content-muted">{sales.change_pct == null ? "A non-zero prior period is needed." : "Against the preceding equal period."}</p></div>
      </dl>
      <p className="mt-4 text-xs leading-relaxed text-content-subtle">{dateLabel(period.start)} – {dateLabel(period.end)} · Comparison window ends: {dateLabel(period.end)}. Latest sale in selection: {dateLabel(sales.as_of)}.</p>
      {sales.series.length > 0 && <SalesChart series={sales.series} />}
      {sales.leaders.length > 0 && <div className="mt-6 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="mb-3 text-left font-semibold text-content">Top SKUs by units sold</caption>
        <thead><tr className="border-b border-line text-xs text-content-muted"><th scope="col" className="pb-3 pr-4 font-medium">Product / SKU</th><th scope="col" className="pb-3 pr-4 text-right font-medium">Units</th><th scope="col" className="pb-3 text-right font-medium">Change</th></tr></thead>
        <tbody>{sales.leaders.map((sku) => <tr key={sku.sku_id} className="border-b border-line last:border-0"><td className="py-3 pr-4"><span className="block font-medium text-content">{sku.product_name}</span><span className="mt-1 block font-mono text-xs text-content-muted">{sku.sku_code}</span></td><td className="py-3 pr-4 text-right tabular-nums text-content">{count(sku.current_units)}</td><td className="py-3 text-right tabular-nums text-content-muted">{changeLabel(sku.change_pct)}</td></tr>)}</tbody>
      </table></div>}
    </>}
  </section>;
}

function ExternalInterest({ data, district, onRefresh, refreshing, notice }: { data: CompanyTrends; district: string; onRefresh: () => void; refreshing: boolean; notice: string }) {
  return <section aria-labelledby="external-interest-title" className="rounded-[20px] border border-line bg-surface p-5 sm:p-6">
    <div className="mb-5 flex items-start gap-3"><span className="rounded-xl bg-surface-3 p-2.5 text-accent"><Globe size={19} /></span><div><h2 id="external-interest-title" className="font-heading text-lg font-semibold text-content">External market interest</h2><p className="mt-1 text-sm leading-relaxed text-content-muted">Relative search interest matched to your catalogue. This index does not measure your sales or market growth.</p></div></div>
    {data.external.items.length === 0 ? <div className="rounded-xl border border-dashed border-line-strong bg-surface-2 p-5"><p className="font-semibold text-content">{district ? "No external data for this district" : "No matching external evidence yet"}</p><p className="mt-2 text-sm leading-relaxed text-content-muted">{district ? "State and city results are kept at their reported level. A district score is shown only when the source reports it." : "External evidence appears here when a source matches your uploaded products or categories."}</p></div> : <>
      <div className="space-y-3">{data.external.items.map((item) => <article key={item.id} className="rounded-xl border border-line p-4">
        <div className="flex items-start justify-between gap-4"><div className="min-w-0"><h3 className="break-words text-sm font-semibold text-content">{item.term}</h3><p className="mt-1 break-words text-xs text-content-muted">Matches: {item.matched_products.join(", ")}</p></div><span className="shrink-0 whitespace-nowrap rounded-lg bg-surface-3 px-2.5 py-1.5 font-mono text-sm font-semibold text-accent">{item.relative_interest == null ? "Index unavailable" : `${count(item.relative_interest)} / 100`}</span></div>
        <p className="mt-3 text-xs leading-relaxed text-content-subtle">{item.source.replace(/_/g, " ")} · {dateLabel(item.captured_at)} · {item.geography_level === "unknown" ? "Geography not reported" : `${item.geography_level[0].toUpperCase()}${item.geography_level.slice(1)}: ${item.district ?? item.city ?? item.state ?? item.region ?? "Not reported"}`}</p>
      </article>)}</div>
      <p className="mt-4 text-xs text-content-subtle">Latest matched evidence: {dateLabel(data.external.as_of)}. Missing signals are never replaced with estimates.</p>
    </>}
    <div className="mt-5 border-t border-line pt-4"><Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} loading={refreshing} onClick={onRefresh}>Refresh market interest</Button>{notice && <p role="status" className="mt-3 text-xs leading-relaxed text-content-muted">{notice}</p>}</div>
  </section>;
}

export const TrendAnalysisPage = () => {
  const industry = useWorkspaceIndustry();
  const tenantId = useAuthStore((session) => session.tenantId);
  return <CompanyTrendWorkspace key={`${tenantId}:${industry}`} industry={industry} tenantId={tenantId} />;
};

function CompanyTrendWorkspace({ industry, tenantId }: { industry: IndustryCode; tenantId: string | null }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"company" | "regional">("company");
  const [days, setDays] = useState("28");
  const [productId, setProductId] = useState("");
  const [skuId, setSkuId] = useState("");
  const [productLabel, setProductLabel] = useState("All products");
  const [skuLabel, setSkuLabel] = useState("All SKUs");
  const [productSearch, setProductSearch] = useState("");
  const [skuSearch, setSkuSearch] = useState("");
  const [state, setState] = useState("");
  const [district, setDistrict] = useState("");
  const [refreshNotice, setRefreshNotice] = useState("");
  const [polling, setPolling] = useState(false);
  useEffect(() => {
    if (!polling) return;
    const timer = setTimeout(() => setPolling(false), 60_000);
    return () => clearTimeout(timer);
  }, [polling]);
  const refreshMarket = useMutation({
    mutationFn: trendsApi.companyRefresh,
    onSuccess: (result) => {
      setRefreshNotice(result.status === "skipped" ? result.reason || "No catalogue terms are available to refresh." : result.status === "running" ? "Market refresh is already running. Saved evidence will update as results arrive." : "Market refresh queued. Saved evidence will update as results arrive.");
      setPolling(result.status !== "skipped");
      void qc.invalidateQueries({ queryKey: ["trends", "company"] });
    },
    onError: () => setRefreshNotice("Market refresh could not be started. Your saved evidence remains available; try again."),
  });
  const productQuery = useDebounced(productSearch), skuQuery = useDebounced(skuSearch);
  const filters = { days: Number(days), product_id: productId || undefined, sku_id: skuId || undefined, state: tab === "regional" ? state || undefined : undefined, district: tab === "regional" ? district || undefined : undefined };
  const company = useQuery({ queryKey: ["trends", "company", tenantId, industry, filters], queryFn: () => trendsApi.company(filters), staleTime: 60_000, refetchInterval: polling ? 5_000 : false });
  const products = useQuery({ queryKey: ["trends", "catalogue", "product", tenantId, industry, productQuery], queryFn: () => trendsApi.catalogue({ kind: "product", q: productQuery, limit: 30 }), staleTime: 60_000 });
  const skus = useQuery({ queryKey: ["trends", "catalogue", "sku", tenantId, industry, skuQuery, productId], queryFn: () => trendsApi.catalogue({ kind: "sku", q: skuQuery, product_id: productId || undefined, limit: 30 }), staleTime: 60_000 });
  const productOptions = [{ value: "", label: "All products" }, ...(products.data?.items ?? []).map((item) => ({ value: item.id, label: item.label, description: item.category }))];
  const skuOptions = [{ value: "", label: "All SKUs" }, ...(skus.data?.items ?? []).map((item) => ({ value: item.id, label: item.label, description: item.product_name }))];

  return <div className="space-y-6" data-industry={industry}>
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div className="max-w-2xl"><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-content-subtle">Trends & insights</p><h1 className="font-heading text-2xl font-semibold tracking-tight text-content sm:text-3xl">Understand demand for your products</h1><p className="mt-2 text-sm leading-relaxed text-content-muted">See what your company is selling and which market signals match your catalogue.</p></div><Button variant="secondary" size="sm" icon={<RefreshCw size={15} />} loading={company.isFetching} onClick={() => { void company.refetch(); void products.refetch(); void skus.refetch(); }}>Refresh</Button></header>
    <div className="flex flex-wrap gap-2 rounded-xl border border-line bg-surface p-1.5" aria-label="Trend views">{([{ id: "company", label: "Company trends", icon: BarChart2 }, { id: "regional", label: "Regional insights", icon: MapPin }] as const).map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)} className={clsx("inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent", tab === id ? "bg-accent text-accent-fg" : "text-content-muted hover:bg-surface-2")}><Icon size={15} />{label}</button>)}</div>
    <Card padding="sm" className="relative z-10">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <SearchableSelect label="Product" value={productId} selectedLabel={productLabel} options={productOptions} loading={products.isFetching} onSearch={setProductSearch} onChange={(value) => { setProductId(value); setProductLabel(productOptions.find((option) => option.value === value)?.label ?? "All products"); setSkuId(""); setSkuLabel("All SKUs"); }} />
        <SearchableSelect label="SKU" value={skuId} selectedLabel={skuLabel} options={skuOptions} loading={skus.isFetching} onSearch={setSkuSearch} onChange={(value) => { setSkuId(value); setSkuLabel(skuOptions.find((option) => option.value === value)?.label ?? "All SKUs"); }} />
        <SearchableSelect label="Period" value={days} options={[{ value: "28", label: "28-day window" }, { value: "56", label: "56-day window" }, { value: "84", label: "84-day window" }]} onChange={setDays} />
        {tab === "regional" && <>
          <SearchableSelect label="State" value={state} options={[{ value: "", label: "All states" }, ...ALL_STATES.map((name) => ({ value: name, label: name }))]} onChange={(value) => { setState(value); setDistrict(""); }} />
          <SearchableSelect label="District" value={district} disabled={!state} options={[{ value: "", label: "All districts" }, ...(INDIA_STATE_DISTRICTS[state] ?? []).map((name) => ({ value: name, label: name }))]} onChange={setDistrict} hint={!state ? "Choose a state first" : state === "Telangana" ? "All 33 Telangana districts" : "District reference is partial for this state"} />
        </>}
      </div>
      {(products.isError || skus.isError) && <p role="status" className="mt-3 text-sm text-amber-700">Catalogue options could not be loaded. Try Refresh.</p>}
    </Card>
    {company.isLoading ? <div role="status" className="rounded-2xl border border-line bg-surface p-8 text-sm text-content-muted">Loading company trends…</div> : company.isError ? <div role="alert" className="rounded-2xl border border-line bg-surface p-6"><h2 className="font-semibold text-content">Company trends could not be loaded</h2><p className="mt-2 text-sm text-content-muted">Your catalogue and sales evidence are currently unavailable.</p><Button className="mt-4" variant="secondary" onClick={() => void company.refetch()}>Try again</Button></div> : company.data && <>
      {company.data.catalogue.sku_count === 0 ? <Card className="text-center"><span className="mx-auto mb-4 inline-flex rounded-2xl bg-surface-3 p-4 text-accent"><Upload size={24} /></span><h2 className="font-heading text-xl font-semibold text-content">Start with your company catalogue</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-content-muted">Add your products and SKUs, then upload sales to see trends for your business.</p><Link to="/workspace/products" className="btn-primary mt-5 inline-flex items-center gap-2">Add products and SKUs <ArrowRight size={16} /></Link></Card> : <>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-content-muted"><span>{count(company.data.catalogue.product_count)} products · {count(company.data.catalogue.sku_count)} SKUs in your catalogue</span>{tab === "regional" && <span className="inline-flex items-center gap-1"><MapPin size={13} />{district ? `${district}, ${state}` : state || "All regions"}</span>}</div>
        <CompanySales data={company.data} /><ExternalInterest data={company.data} district={tab === "regional" ? district : ""} onRefresh={() => refreshMarket.mutate()} refreshing={refreshMarket.isPending} notice={refreshNotice} />
      </>}
    </>}
  </div>;
}
