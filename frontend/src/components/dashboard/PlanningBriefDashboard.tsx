import { Link } from "react-router-dom";
import { AISummary } from "@/components/ai/AISummary";
import { WhatsAppStatus } from "@/components/dashboard/WhatsAppStatus";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Database,
  PackageCheck,
  Plug,
  RefreshCw,
  ShoppingBag,
  TrendingUp,
} from "@/components/ui/icons";
import { decisionsApi } from "@/api/decisions";
import { forecastsApi, forecastConfidenceApi } from "@/api/forecasts";
import { dataQualityApi } from "@/api/dataQuality";
import { integrationsApi } from "@/api/integrations";
import { salesAnalyticsApi } from "@/api/salesAnalytics";
import { inventoryApi } from "@/api/inventory";
import { INTEGRATION_CATALOG_KEY, invalidatePlanningData } from "@/api/planningKeys";
import { weeklyHistory } from "@/components/dashboard/dashboardData";
import { getErrorMessage } from "@/utils/errors";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getProductImage, useProductImagesStore } from "@/stores/productImages";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import type { ForecastRow, IndustryCode } from "@/types/api";

/**
 * Portfolio line = sum of per-SKU P50s (exact for expectations). The band is
 * the sum of per-SKU P10s and P90s, which is NOT a calibrated portfolio
 * P10–P90: summed quantiles assume every SKU lands in its tail together. It is
 * labelled as exactly that on screen; no joint samples exist to do better.
 */
function aggregateForecast(rows: ForecastRow[]): ForecastRow[] {
  const byDate = new Map<string, ForecastRow>();
  rows.forEach((row) => {
    const current = byDate.get(row.forecast_date) ?? {
      sku_id: "portfolio",
      forecast_date: row.forecast_date,
      p10: 0,
      p50: 0,
      p90: 0,
    };
    current.p10 += row.p10;
    current.p50 += row.p50;
    current.p90 += row.p90;
    byDate.set(row.forecast_date, current);
  });
  return Array.from(byDate.values()).sort((a, b) => a.forecast_date.localeCompare(b.forecast_date));
}

function SummaryItem({
  icon: Icon,
  label,
  value,
  detail,
  tone = "default",
  testId,
}: {
  icon: typeof ShoppingBag;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
  testId?: string;
}) {
  const tones = {
    default: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/12 dark:text-emerald-300",
    success: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/12 dark:text-emerald-300",
    warning: "bg-amber-50 text-amber-700 dark:bg-amber-500/12 dark:text-amber-300",
    danger: "bg-rose-50 text-rose-700 dark:bg-rose-500/12 dark:text-rose-300",
    info: "bg-sky-50 text-sky-700 dark:bg-sky-500/12 dark:text-sky-300",
  };
  return (
    <div className="flex items-center gap-3 py-2.5">
      <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${tones[tone]}`}><Icon size={17} /></span>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-content-subtle">{label}</p>
        <p data-testid={testId} className="mt-0.5 font-mono text-lg font-semibold leading-none text-content">{value}</p>
        <p className="mt-0.5 text-xs text-content-muted">{detail}</p>
      </div>
    </div>
  );
}

export const PlanningBriefDashboard = () => {
  const industry = useWorkspaceIndustry();
  const images = useProductImagesStore((state) => state.images);
  const { decodeToken } = useAuthStore();
  const { formatPrice } = useFormattedCurrency();
  const queryClient = useQueryClient();
  const decoded = decodeToken();

  const decisions = useQuery({
    queryKey: ["decisions", industry, "open"],
    queryFn: () => decisionsApi.list({ status: "open", limit: 20 }),
  });
  const forecast = useQuery({
    queryKey: ["dashboard-forecast", industry],
    queryFn: () => forecastsApi.generate({ horizon: 12, force_zero_shot: true }),
    retry: false,
  });
  // Weekly, to match the weekly forecast buckets (deep audit F4).
  const history = useQuery({
    queryKey: ["dashboard-history", industry, "week"],
    queryFn: () => salesAnalyticsApi.timeseries("week", 84),
    retry: false,
  });
  const confidence = useQuery({
    queryKey: ["forecast-confidence", industry],
    queryFn: () => forecastConfidenceApi.list(100),
    retry: false,
  });
  const quality = useQuery({
    queryKey: ["data-quality", industry],
    queryFn: dataQualityApi.report,
    retry: false,
  });
  const integrations = useQuery({
    queryKey: INTEGRATION_CATALOG_KEY,
    queryFn: integrationsApi.catalog,
    retry: false,
  });
  const coverage = useQuery({
    queryKey: ["inventory-coverage", industry],
    queryFn: () => inventoryApi.coverage(),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: (id: string) => decisionsApi.accept(id),
    onSuccess: () => toast.success("Recommendation accepted and added to the ROI ledger"),
    // e.g. 409 for an expired recommendation: say why, never fail silently.
    onError: (e) => toast.error(getErrorMessage(e, "Could not accept the recommendation")),
    onSettled: () => void invalidatePlanningData(queryClient),
  });

  const response = decisions.data;
  const decisionsFailed = decisions.isError;
  const open = response?.decisions ?? [];
  const primary = open[0];
  const hasDecision = Boolean(primary);
  const totals = response?.totals;
  const portfolioConfidence = confidence.data?.portfolio_confidence ?? null;
  const lowConfidenceSkus = (confidence.data?.skus ?? []).filter(
    (s) => s.band === "low" || s.band === "insufficient",
  ).length;
  const criticalIssues = quality.data?.critical ?? 0;
  const leadTimeAssumed = (coverage.data?.skus ?? []).filter((s) => s.lead_time_assumed).length;
  const warnings = quality.data?.issues_found;
  const stockoutRisk = Math.max(
    totals?.critical ?? 0,
    open.filter((decision) => {
      const cover = decision.inputs?.days_of_cover;
      return typeof cover === "number" && typeof decision.inputs.lead_time_days === "number" && cover <= decision.inputs.lead_time_days;
    }).length,
  );
  const currency = totals?.currency ?? "INR";
  const fmt = (value: number) => formatPrice(value, currency, { compact: true });
  const unavailable = "Unavailable";
  const reasons = primary?.reasons ?? [];
  const historyRows = history.data ? weeklyHistory(history.data) : [];
  const hasHistory = historyRows.some((point) => point.actual !== null);
  const forecastRows = aggregateForecast(forecast.data?.rows ?? []);
  const fallbackDescriptor: Record<IndustryCode, string> = {
    fashion: "jacket",
    electronics: "headphones",
    pharma: "ibuprofen tablets",
    agrocenter: "poultry feed",
    hardware: "cement bag",
  };
  const productImage = getProductImage(
    primary?.sku_id ?? "dashboard-primary",
    industry,
    images,
    primary?.sku_code ?? fallbackDescriptor[industry],
  );
  const cover = primary?.inputs?.days_of_cover;
  const revenueProtected = primary?.economics?.revenue_protected ?? 0;
  const suggestedUnits = primary?.recommended_units ?? 0;
  const plannerName = (decoded?.name as string | undefined)?.split(" ")[0] ?? "Sanket";

  return (
    <div className="animate-fade-in space-y-3">
      <AISummary feature="planning_brief" runId={forecast.data?.run_id} contextKey={JSON.stringify([industry, decisions.data, forecast.data?.run_id, quality.data, coverage.data])} />
      <header className="flex flex-col gap-3 rounded-2xl border border-line bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-xl font-semibold tracking-tight text-content">
            {decisionsFailed
              ? `Good morning, ${plannerName} — part of your planning brief is unavailable`
              : hasDecision
                ? `Good morning, ${plannerName} — ${open.length} decision${open.length === 1 ? "" : "s"} need you`
                : `Good morning, ${plannerName} — your planning brief is ready`}
          </h1>
          <p className="mt-0.5 text-sm text-content-muted" role={decisionsFailed ? "alert" : undefined}>
            {decisionsFailed
              ? "Decisions could not be loaded — the queue is unknown, not empty. Use Refresh brief to retry."
              : decisions.isPending
                ? "Loading decisions…"
                : hasDecision
                  ? "Here is the most important action to review today."
                  : "No open order decision currently requires approval."}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} />}
          // Every panel here derives from the same stock/forecast inputs, so they
          // refresh together (deep audit F9).
          onClick={() => {
            void invalidatePlanningData(queryClient);
            void forecast.refetch();
          }}
          loading={decisions.isFetching || forecast.isFetching || quality.isFetching || coverage.isFetching}
        >
          Refresh brief
        </Button>
      </header>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.9fr)_minmax(290px,0.95fr)]">
        <div className="min-w-0 space-y-3">
          <section className={`rounded-2xl border p-4 dark:bg-surface ${hasDecision ? "border-emerald-700/20 bg-[color-mix(in_srgb,var(--surface)_88%,#DFF4EF)]" : "border-sky-700/20 bg-[color-mix(in_srgb,var(--surface)_90%,#E7F2F5)]"}`}>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 gap-3">
                <img
                  src={productImage}
                  alt={primary?.sku_code ? `${primary.sku_code} product` : `${industry} catalogue product`}
                  className="h-16 w-16 shrink-0 rounded-xl border border-line bg-surface-2 object-cover"
                />
                <div className="min-w-0">
                  <p className="font-mono text-xs font-semibold uppercase text-content-muted">{primary?.sku_code ?? `${industry} planning`}</p>
                  <h2 className="mt-1 font-heading text-xl font-semibold text-content">
                    {hasDecision ? "Review the recorded stock recommendation" : "Review demand history and stock coverage"}
                  </h2>
                  <p className="mt-0.5 text-sm text-content-muted">
                    {hasDecision
                      ? "Based on recorded stock, demand and lead-time inputs."
                      : "Sanket will only show an order action after it can support it with auditable inventory and lead-time inputs."}
                  </p>
                </div>
              </div>
              {portfolioConfidence != null && portfolioConfidence > 0 && (
                <span className="self-start rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                  {portfolioConfidence}% confidence
                </span>
              )}
            </div>

            {hasDecision ? (
              <div className="mt-4 border-t border-line pt-3">
                <div className="mb-2 flex items-center justify-between gap-4">
                  <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-content-subtle">Why this is happening</h3>
                </div>
                {reasons.length ? (
                  <ul className="space-y-2">
                    {reasons.map((reason, index) => (
                      <li key={`${reason.code}-${index}`} className="text-sm text-content">{reason.text}</li>
                    ))}
                  </ul>
                ) : <p className="text-sm text-content-muted">No supporting reasons recorded. Review the decision inputs before acting.</p>}
              </div>
            ) : (
              <div className="mt-4 border-t border-line pt-3">
                <div className="flex items-center justify-between gap-4">
                  <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-content-subtle">Decision readiness</h3>
                  <span className="text-xs text-content-subtle">No recommendation invented</span>
                </div>
                <dl className="mt-2 grid gap-2 sm:grid-cols-3">
                  <div className="rounded-xl bg-surface/70 px-3 py-2"><dt className="text-xs text-content-muted">Demand history</dt><dd className="mt-0.5 text-sm font-semibold text-content">{history.isError ? unavailable : hasHistory ? "Available" : "Needs data"}</dd></div>
                  <div className="rounded-xl bg-surface/70 px-3 py-2"><dt className="text-xs text-content-muted">Forecast signal</dt><dd className="mt-0.5 text-sm font-semibold text-content">{forecastRows.length ? "Available" : "Needs data"}</dd></div>
                  <div className="rounded-xl bg-surface/70 px-3 py-2"><dt className="text-xs text-content-muted">Order action</dt><dd className="mt-0.5 text-sm font-semibold text-content">{decisionsFailed ? unavailable : "None open"}</dd></div>
                </dl>
              </div>
            )}

            <div className="mt-4 flex flex-col gap-3 border-t border-line pt-3 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-content-subtle">{hasDecision ? "Recommendation" : "Next planning step"}</p>
                <p className="mt-1 font-heading text-xl font-semibold text-content">
                  {primary?.headline ?? (suggestedUnits ? `Order ${suggestedUnits.toLocaleString()} units` : "Review stock coverage before placing an order")}
                </p>
                {hasDecision ? (
                  <p className="mt-1 text-xs text-content-muted">
                    {typeof cover === "number" ? `${cover.toFixed(0)} days cover` : "Coverage pending"} · Service level target: {typeof primary?.inputs.service_level === "number" ? `${Math.round(primary.inputs.service_level * 100)}%` : "Unavailable"}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-content-muted">No order recommendation is shown because Sanket has not produced an auditable action for this industry.</p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {typeof cover === "number" && <div className="border-r border-line pr-3"><p className="font-mono text-lg font-semibold">{cover.toFixed(0)} days</p><p className="text-xs text-content-subtle">Cover left</p></div>}
                {revenueProtected > 0 && <div><p className="font-mono text-lg font-semibold">{fmt(revenueProtected)}</p><p className="text-xs text-content-subtle">Revenue protected</p></div>}
              </div>
              <div className="flex flex-wrap gap-2">
                <Link to={hasDecision ? "/workspace/decisions" : "/workspace/inventory"}><Button variant="secondary">{hasDecision ? "Review order" : "Review inventory"}</Button></Link>
                {!hasDecision && <Link to="/workspace/forecasts"><Button>Open forecast</Button></Link>}
                {primary && <Button icon={<Check size={14} />} onClick={() => accept.mutate(primary.id)} loading={accept.isPending}>Accept recommendation</Button>}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-3 text-xs" aria-label="What the confidence and warnings are made of">
              {lowConfidenceSkus > 0 && <Link to="/workspace/forecasts" className="font-semibold text-amber-700 underline-offset-2 hover:underline dark:text-amber-300">{lowConfidenceSkus} low-confidence SKU{lowConfidenceSkus === 1 ? "" : "s"}</Link>}
              {criticalIssues > 0 && <Link to="/workspace/data-quality" className="font-semibold text-rose-700 underline-offset-2 hover:underline dark:text-rose-300">{criticalIssues} critical data issue{criticalIssues === 1 ? "" : "s"}</Link>}
              {leadTimeAssumed > 0 && <Link to="/workspace/inventory" className="font-semibold text-amber-700 underline-offset-2 hover:underline dark:text-amber-300">{leadTimeAssumed} SKU{leadTimeAssumed === 1 ? " uses" : "s use"} an assumed lead time</Link>}
              <span className="text-content-subtle">Confidence is a data-quality heuristic, not measured forecast accuracy — see Forecast Accuracy for held-out results.</span>
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-surface p-4">
            <div className="mb-1 flex items-start justify-between gap-4">
              <div>
                <h2 className="font-heading text-base font-semibold text-content">Forecast snapshot</h2>
                <p className="mt-0.5 text-xs text-content-muted">Weekly actuals (complete Monday–Sunday UTC weeks) against expected weekly demand. The shaded band is the sum of per-SKU P10–P90 ranges — not a calibrated portfolio interval.</p>
              </div>
              <Link to="/workspace/forecasts" className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--accent)]">Open forecast <ArrowRight size={13} /></Link>
            </div>
            {forecast.isError ? (
              <p role="alert" className="py-6 text-sm text-content-muted">Forecast service unavailable. Open Forecasts to retry; no substitute prediction is shown.</p>
            ) : forecastRows.length ? (
              <ForecastChart rows={forecastRows} history={historyRows} height={180} unitLabel="units / week" />
            ) : <p className="py-6 text-sm text-content-muted">{forecast.isFetching ? "Generating forecast…" : "No forecast available. Upload sufficient sales history to begin."}</p>}
          </section>
        </div>

        <aside className="min-w-0 space-y-3">
          <section className="rounded-2xl border border-line bg-surface px-4 py-3">
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-content-muted">Planning summary</h2>
            <div className="mt-1 divide-y divide-line">
              <SummaryItem icon={ShoppingBag} label="Orders due" value={decisionsFailed ? unavailable : String(totals?.purchase_orders ?? open.length)} detail={decisionsFailed ? "decisions could not be loaded" : `${(totals?.units_to_order ?? 0).toLocaleString()} units`} />
              <SummaryItem icon={PackageCheck} label="Revenue at risk (estimate)" value={decisionsFailed || totals?.revenue_protected == null ? unavailable : fmt(totals.revenue_protected)} detail={!decisionsFailed && totals && totals.revenue_protected == null ? "needs a unit price for every open order" : "covered if the open orders are placed"} tone="success" />
              <SummaryItem icon={AlertTriangle} label="Stockout approaching" value={decisionsFailed ? unavailable : String(stockoutRisk)} detail="SKUs at risk" tone="warning" />
              <SummaryItem icon={TrendingUp} label="Forecast confidence" value={confidence.isError ? unavailable : portfolioConfidence != null ? `${portfolioConfidence}%` : "—"} detail={lowConfidenceSkus ? `${lowConfidenceSkus} SKUs low · heuristic, not accuracy` : "heuristic score, not measured accuracy"} tone="info" />
              <SummaryItem icon={AlertTriangle} label="Data warnings" testId="summary-data-warnings" value={quality.isError ? unavailable : warnings == null ? "…" : String(warnings)} detail={quality.isError ? "data-quality check failed" : criticalIssues ? `${criticalIssues} critical` : "need attention"} tone={quality.isError || (warnings ?? 0) > 0 ? "danger" : "success"} />
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-surface p-3">
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-content-muted">System readiness</h2>
            <dl className="mt-2 grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
              <div className="flex items-center gap-3"><Database size={17} className="text-emerald-600" /><div><dt className="text-xs font-semibold text-content">Data freshness</dt><dd className="text-xs text-content-subtle">{quality.isError ? "Check failed" : quality.data ? "Audit updated" : "Checking sources"}</dd></div></div>
              <div className="flex items-center gap-3"><Plug size={17} className="text-emerald-600" /><div><dt className="text-xs font-semibold text-content">Integrations</dt><dd className="text-xs text-content-subtle">{integrations.isError ? unavailable : integrations.data ? `${integrations.data.connected} connected` : "Checking…"}</dd></div></div>
              <WhatsAppStatus />
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
};
