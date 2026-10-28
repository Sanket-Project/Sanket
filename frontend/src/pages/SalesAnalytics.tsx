import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { Activity, ShoppingCart } from "@/components/ui/icons";
import { salesAnalyticsApi, type SalesBucket, type TopProductPeriod } from "@/api/salesAnalytics";
import { Card } from "@/components/ui/Card";
import { BranchSales } from "@/components/charts/BranchSales";
import { PageLoader } from "@/components/ui/Spinner";
import { LiveIndicator } from "@/components/realtime/LiveIndicator";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { fmtNumber } from "@/utils/format";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { apiClient } from "@/api/client";
import { ClientReports, type ClientReportData } from "@/components/dashboard/ClientReports";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuthStore } from "@/stores/auth";
import { getErrorMessage } from "@/utils/errors";

type Granularity = "day" | "week" | "month";
type DateRange = "30" | "90" | "365";
const dateLabel = (date: string) => format(parseISO(date), "d MMM yyyy");
const controlClass = "min-h-11 rounded-xl border border-line bg-surface px-3 py-2 text-sm text-content";

export const SalesAnalyticsPage = () => {
  const industry = useWorkspaceIndustry();
  const { subscribe } = useWebSocket();
  const cache = useQueryClient();
  const role = useAuthStore(state => state.role);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deletion = useMutation({ mutationFn: salesAnalyticsApi.deleteAll, onSuccess: async () => {
    setConfirmDelete(false);
    await Promise.all(["client-reports", "sales-summary", "sales-timeseries", "sales-top-products", "sales-branches"].map(key => cache.invalidateQueries({ queryKey: [key] })));
  }});
  const deleteControl = (role === "owner" || role === "admin") && <>
    <button className="rounded-lg border border-red-600 px-4 py-3 text-sm font-medium text-red-700" onClick={() => setConfirmDelete(true)}>Delete all sales</button>
    <ConfirmDialog open={confirmDelete} onClose={() => { setConfirmDelete(false); deletion.reset(); }} title="Delete all sales?" confirmLabel="Confirm delete all sales" loading={deletion.isPending} onConfirm={() => deletion.mutate()} message={<><p>This permanently deletes sales history, related returns and imported reports for {industry}. Products and inventory are kept.</p>{deletion.isError && <p role="alert" className="mt-3 text-sm text-red-700">{getErrorMessage(deletion.error, "Sales could not be deleted. Please try again.")}</p>}</>} />
  </>;
  const { formatPrice } = useFormattedCurrency();
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [dateRange, setDateRange] = useState<DateRange>("365");
  const [topPeriod, setTopPeriod] = useState<TopProductPeriod>("year");
  const [metric, setMetric] = useState<"revenue" | "units">("revenue");
  const reports = useQuery({
    queryKey: ["client-reports", industry],
    queryFn: async () => (await apiClient.get<{ status: string; report: ClientReportData | null }>("/analytics/sales/client-reports")).data,
  });
  const transactionsEnabled = reports.isSuccess && !reports.data?.report;
  const summaryQuery = useQuery({ queryKey: ["sales-summary", industry], queryFn: () => salesAnalyticsApi.summary(), enabled: transactionsEnabled, refetchInterval: 60_000 });
  const seriesQuery = useQuery({ queryKey: ["sales-timeseries", industry, granularity, dateRange], queryFn: () => salesAnalyticsApi.timeseries(granularity, Number(dateRange)), enabled: transactionsEnabled, refetchInterval: 60_000 });
  const topQuery = useQuery({ queryKey: ["sales-top-products", industry, topPeriod], queryFn: () => salesAnalyticsApi.topProducts(topPeriod, 10), enabled: transactionsEnabled, refetchInterval: 60_000 });
  const branchesQuery = useQuery({ queryKey: ["sales-branches", industry, dateRange, granularity], queryFn: () => salesAnalyticsApi.branches(Number(dateRange), granularity), enabled: transactionsEnabled, refetchInterval: 60_000 });

  useEffect(() => {
    let timer: number | undefined;
    const unsubscribe = subscribe(event => {
      if (event.type !== "sale.created" || (event.industry && event.industry !== industry)) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        for (const key of ["sales-summary", "sales-timeseries", "sales-top-products", "sales-branches"]) {
          void cache.invalidateQueries({ queryKey: [key, industry] });
        }
      }, 500);
    });
    return () => { unsubscribe(); window.clearTimeout(timer); };
  }, [subscribe, cache, industry]);

  const series = seriesQuery.data;
  const chartData = useMemo(() => (series?.series ?? []).map(point => ({ bucket: point.bucket, revenue: point.gross_revenue, units: point.units_sold })), [series]);
  const observed = (series?.series ?? []).filter(point => point.units_sold != null);
  const mixed = (series?.currencies.length ?? 0) > 1;
  const chartMetric = mixed ? "units" : metric;
  const period = series?.series.length ? `${dateLabel(series.series[0].bucket)} – ${dateLabel(summaryQuery.data?.as_of ?? new Date().toISOString())}` : "Selected date range";
  const periodUnits = observed.reduce((sum, point) => sum + (point.units_sold ?? 0), 0);
  const periodRevenue = observed.reduce((sum, point) => sum + (point.gross_revenue ?? 0), 0);
  const periodMoney = mixed ? series?.currencies.map(currency => {
    const amount = observed.reduce((sum, point) => sum + (point.revenue_by_currency?.[currency] ?? 0), 0);
    return formatPrice(amount, currency);
  }).join(" · ") : formatPrice(periodRevenue, series?.currency);
  const month = summaryQuery.data?.month;
  const completed = series?.current_bucket ? series.series.filter(point => point.bucket < series.current_bucket!).slice(-2) : [];
  const [earlier, latest] = completed;
  const before = chartMetric === "revenue" ? earlier?.gross_revenue : earlier?.units_sold;
  const after = chartMetric === "revenue" ? latest?.gross_revenue : latest?.units_sold;
  const trend = before != null && after != null && before > 0
    ? `${chartMetric === "revenue" ? "Sales" : "Items sold"} ${after === before ? "stayed the same" : `${after > before ? "rose" : "fell"} ${(Math.abs(after - before) / before * 100).toFixed(1)}%`} in ${format(parseISO(latest.bucket), granularity === "month" ? "MMM yyyy" : "'the period starting' d MMM yyyy")} compared with ${format(parseISO(earlier.bucket), granularity === "month" ? "MMM yyyy" : "d MMM yyyy")}.`
    : null;

  if (reports.isLoading) return <PageLoader />;
  if (reports.isError) return <Retry title="Client reports unavailable" button="Retry reports" onRetry={() => void reports.refetch()} />;
  if (reports.data?.report) return <div className="space-y-4">{deleteControl}<ClientReports report={reports.data.report} /></div>;
  if (summaryQuery.isLoading) return <PageLoader />;
  if (summaryQuery.isError || !summaryQuery.data) return <Retry title="Sales unavailable" button="Retry sales" onRetry={() => void summaryQuery.refetch()} />;
  const summary = summaryQuery.data;

  return <section aria-label="Sales performance overview" className="sales-overview space-y-6">
    {deleteControl}
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div>
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-content-muted"><Activity size={15} aria-hidden="true" /> Sales analytics</p>
        <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight text-content sm:text-4xl">Your sales, at a glance</h1>
        <p className="mt-2 text-sm text-content-muted">How much you sold. What sold best. Where it happened.</p>
      </div>
      <label className="flex flex-col gap-1 text-xs font-medium text-content-muted">Show sales for
        <select aria-label="Sales date range" className={controlClass} value={dateRange} onChange={event => setDateRange(event.target.value as DateRange)}>
          <option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="365">Last 12 months</option>
        </select>
      </label>
    </header>

    <Card className="sales-summary !border-0 !bg-transparent !p-0 !shadow-none">
      <div className="sales-summary-grid">
        <div className="sales-summary-primary">
          <p className="text-sm opacity-80">Sales before returns</p>
          <p className="mt-3 break-words font-heading text-4xl font-semibold tracking-tight sm:text-5xl">{seriesQuery.isLoading ? "Loading…" : seriesQuery.isError || !observed.length ? "Unavailable" : periodMoney}</p>
          <p className="mt-4 text-sm opacity-80">{period}</p>
          <p className="mt-2 text-xs opacity-80">Full days, weeks or months are shown. The first may start before your selected range.</p>
        </div>
        <div className="sales-summary-secondary">
          <p className="font-mono text-3xl font-semibold">{seriesQuery.isLoading ? "…" : seriesQuery.isError || !observed.length ? "—" : fmtNumber(periodUnits)}</p>
          <p className="mt-1 text-sm opacity-80">items sold, before returns</p>
          <p className="mt-4 text-xs leading-relaxed opacity-80">{mixed ? "Mixed currencies are shown separately." : "Your recorded sales in the date range above."}</p>
        </div>
        <div className="sales-summary-secondary"><p className="text-sm text-content-muted">This month’s sales</p><p className="mt-3 break-words font-mono text-2xl font-semibold text-content"><BucketMoney bucket={summary.month} currency={summary.currency} /></p><p className="mt-3 text-xs text-content-muted">{dateLabel(summary.month.period_start)} – {dateLabel(summary.as_of)} · month in progress</p></div>
      </div>
    </Card>

    <div className="sales-analysis-grid">
    <Card title="How sales changed" description="Higher points mean more sales. Gaps mean there are no records.">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 rounded-xl bg-surface-2 p-1" aria-label="Chart grouping">
          {([['day', 'Daily'], ['week', 'Weekly'], ['month', 'Monthly']] as const).map(([value, label]) => <button key={value} aria-pressed={granularity === value} onClick={() => setGranularity(value)} className={`min-h-11 rounded-lg px-3 text-sm ${granularity === value ? "bg-[var(--accent)] text-[var(--accent-fg)]" : "text-content-muted"}`}>{label}</button>)}
        </div>
        {!mixed && <label className="text-xs text-content-muted">Chart shows <select aria-label="Chart measure" className={controlClass} value={metric} onChange={event => setMetric(event.target.value as typeof metric)}><option value="revenue">Sales amount</option><option value="units">Items sold</option></select></label>}
      </div>
      {seriesQuery.isLoading ? <p className="py-16 text-center text-sm text-content-muted">Loading sales history…</p> : seriesQuery.isError ? <Retry title="Sales history unavailable" button="Retry history" onRetry={() => void seriesQuery.refetch()} /> : !observed.length ? <EmptyState title="No sales history for this date range" /> : <>
        {trend && <p className="mb-5 text-base font-medium text-content">{trend}</p>}
        {mixed && <p className="mb-4 text-sm text-content-muted">Amounts use different currencies. This chart compares items sold instead.</p>}
        <div role="img" aria-label={`${chartMetric === "revenue" ? "Sales amount" : "Items sold"} by ${granularity}. Exact values are in the sales history table below.`}>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 15, right: 16, left: 8, bottom: 10 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 6" stroke="var(--border)" />
              <XAxis dataKey="bucket" tickFormatter={value => format(parseISO(value), granularity === "month" ? "MMM yy" : "d MMM")} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={32} />
              <YAxis width={76} tickFormatter={value => chartMetric === "revenue" ? formatPrice(value as number, series?.currency, { compact: true }) : fmtNumber(value as number)} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, color: "var(--text)", fontSize: 12 }} labelFormatter={value => dateLabel(String(value))} formatter={(value: number) => [chartMetric === "revenue" ? formatPrice(value, series?.currency) : fmtNumber(value), chartMetric === "revenue" ? "Sales before returns" : "Items sold"]} />
              <Line type="linear" dataKey={chartMetric} stroke="var(--accent)" strokeWidth={3} dot={chartData.length < 16} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-3 text-xs text-content-muted">The latest {granularity} is still in progress. A zero means no sales were recorded after trading began; a gap means no history is available.</p>
        <details className="mt-4 border-t border-line pt-3">
          <summary className="cursor-pointer py-2 text-sm font-medium text-content">See exact sales history</summary>
          <div className="max-h-80 overflow-auto"><table className="w-full text-left text-sm text-content"><caption className="sr-only">Sales history, before returns</caption><thead><tr><th scope="col" className="py-3">Period starting</th><th scope="col" className="p-3 text-right">Items sold</th><th scope="col" className="py-3 text-right">Sales</th></tr></thead><tbody>{series?.series.map(point => <tr key={point.bucket} className="border-t border-line"><th scope="row" className="py-3 text-left font-normal">{dateLabel(point.bucket)}</th><td className="p-3 text-right font-mono">{point.units_sold == null ? "No records" : fmtNumber(point.units_sold)}</td><td className="py-3 text-right font-mono">{point.units_sold == null ? "No records" : point.gross_revenue == null ? Object.entries(point.revenue_by_currency ?? {}).map(([code, amount]) => formatPrice(amount, code)).join(" · ") || "Unavailable" : formatPrice(point.gross_revenue, series.currency)}</td></tr>)}</tbody></table></div>
        </details>
      </>}
    </Card>

    <Card title="What sold best" description="Ranked by items sold. Choose the product reporting period below.">
      <label className="mb-5 flex flex-wrap items-center gap-3 text-sm text-content-muted">Product sales period
        <select aria-label="Product sales period" value={topPeriod} onChange={event => setTopPeriod(event.target.value as TopProductPeriod)} className={controlClass}><option value="today">Today</option><option value="week">This week</option><option value="month">This month</option><option value="year">This year</option><option value="all">All time</option></select>
      </label>
      {topQuery.isLoading ? <p className="py-8 text-sm text-content-muted">Loading products…</p> : topQuery.isError ? <Retry title="Product sales unavailable" button="Retry products" onRetry={() => void topQuery.refetch()} /> : !topQuery.data?.products.length ? <EmptyState /> : <ol className="divide-y divide-line">{topQuery.data.products.map((product, index) => <li key={product.sku_id} className="flex flex-wrap items-center justify-between gap-4 py-4">
        <div className="flex min-w-0 items-center gap-4"><span aria-hidden="true" className="font-mono text-sm text-content-subtle">{String(index + 1).padStart(2, "0")}</span><div className="min-w-0"><p className="break-words font-medium text-content">{product.product_name}</p><p className="mt-1 break-all text-xs text-content-muted">Product code: {product.sku_code}</p></div></div>
        <div className="ml-auto text-right"><p className="font-mono font-semibold text-content">{fmtNumber(product.units_sold)} <span className="font-sans text-xs font-normal text-content-muted">items sold</span></p><p className="mt-1 font-mono text-sm text-content-muted">{formatPrice(product.gross_revenue, product.currency)}</p>{product.returns > 0 && <p className="mt-1 text-xs text-content-muted">{fmtNumber(product.returns)} returned</p>}</div>
      </li>)}</ol>}
    </Card>

    </div>
    {branchesQuery.isError ? <Retry title="Location comparison unavailable" button="Retry locations" onRetry={() => void branchesQuery.refetch()} /> : <BranchSales grouping="location" period={branchesQuery.data?.period_start ? `${dateLabel(branchesQuery.data.period_start)} – ${dateLabel(branchesQuery.data.as_of)}` : period} rows={(branchesQuery.data?.branches ?? []).map(row => ({ name: row.name, amount: row.gross_revenue, units: row.units_sold, currency: row.currency, revenue_by_currency: row.revenue_by_currency }))} unassigned={branchesQuery.data?.unassigned_records} />}


    <Card title="Today · live feed" description={`Recorded totals · updated ${format(parseISO(summary.as_of), "d MMM, HH:mm")} · times shown in your local timezone`} action={<LiveIndicator />}>
      <div className="grid gap-5 sm:grid-cols-3"><div><p className="text-sm text-content-muted">Sales before returns</p><p className="mt-2 font-mono text-xl font-semibold text-content"><BucketMoney bucket={summary.today} currency={summary.currency} /></p></div><div><p className="text-sm text-content-muted">Items sold</p><p className="mt-2 font-mono text-xl font-semibold text-content">{fmtNumber(summary.today.units_sold)}</p></div><div><p className="text-sm text-content-muted">Sales records</p><p className="mt-2 font-mono text-xl font-semibold text-content">{fmtNumber(summary.today.transactions)}</p><p className="mt-1 text-xs text-content-muted">{summary.today.returns ? `${fmtNumber(summary.today.returns)} items returned` : "No returns today"}</p></div></div>
    </Card>

    <details className="rounded-[20px] border border-line bg-surface p-6">
      <summary className="cursor-pointer py-1 font-medium text-content">Calendar totals & comparisons</summary>
      <p className="mt-3 text-sm text-content-muted">Comparisons use the same elapsed time in the previous calendar period. Sales amounts are before returns. Sales records may contain multiple items.</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">{([['This year', summary.year, 'the same elapsed period last year'], ['This month', summary.month, 'the same elapsed period last month'], ['This week', summary.week, 'the same elapsed period last week']] as const).map(([label, bucket, baseline]) => <div key={label} className="rounded-xl bg-surface-2 p-4"><p className="text-sm text-content-muted">{label}</p><p className="mt-2 break-words font-mono text-xl font-semibold text-content"><BucketMoney bucket={bucket} currency={summary.currency} /></p><p className="mt-2 text-xs text-content-muted">{fmtNumber(bucket.units_sold)} items sold</p><p className="mt-2 text-xs text-content-muted">{bucket.revenue_delta == null ? "Comparison unavailable" : `${Math.abs(bucket.revenue_delta * 100).toFixed(1)}% ${bucket.revenue_delta >= 0 ? "more" : "less"} sales`} · vs {baseline}</p></div>)}</div>
      <p className="mt-4 text-sm text-content-muted">Average sales amount per record this month: {month?.gross_revenue == null || !month.transactions ? "Unavailable" : formatPrice(month.gross_revenue / month.transactions, month.currency)}</p>
    </details>
  </section>;
};

function BucketMoney({ bucket, currency }: { bucket: SalesBucket; currency: string | null }) {
  const { formatPrice } = useFormattedCurrency();
  return <>{bucket.gross_revenue != null ? formatPrice(bucket.gross_revenue, bucket.currency ?? currency) : Object.entries(bucket.revenue_by_currency).map(([code, value]) => formatPrice(value, code)).join(" · ") || "Unavailable"}{bucket.gross_revenue == null && <span className="mt-1 block font-sans text-xs font-normal text-content-muted">Mixed currencies · shown separately</span>}</>;
}
function Retry({ title, button, onRetry }: { title: string; button: string; onRetry: () => void }) {
  return <div role="alert" className="rounded-xl border border-line bg-surface p-5"><p className="font-medium text-content">{title}</p><p className="mt-1 text-sm text-content-muted">We couldn't load these numbers. Try again.</p><button onClick={onRetry} className="mt-3 min-h-11 rounded-lg border border-line px-4 py-2 text-sm font-medium text-content">{button}</button></div>;
}
function EmptyState({ title = "No sales recorded for this period" }: { title?: string }) {
  return <div className="flex flex-col items-center py-10 text-center"><ShoppingCart size={28} aria-hidden="true" className="mb-3 text-content-subtle" /><p className="font-medium text-content">{title}</p><p className="mt-2 max-w-sm text-sm text-content-muted">Try another period, or connect a sales source and import your history.</p><Link to="/workspace/integrations" className="mt-4 rounded-lg border border-line px-4 py-3 text-sm font-medium text-content">Connect a sales source</Link></div>;
}
