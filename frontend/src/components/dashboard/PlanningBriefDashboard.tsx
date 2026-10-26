import { Link } from "react-router-dom";
import { WhatsAppStatus } from "@/components/dashboard/WhatsAppStatus";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Check,
  CircleDollarSign,
  CloudRain,
  Database,
  Megaphone,
  PackageCheck,
  Plug,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  TrendingUp,
} from "@/components/ui/icons";
import type { AppIcon } from "@/components/ui/icons";
import { decisionsApi } from "@/api/decisions";
import { forecastsApi, forecastConfidenceApi } from "@/api/forecasts";
import { dataQualityApi } from "@/api/dataQuality";
import { integrationsApi } from "@/api/integrations";
import { salesAnalyticsApi } from "@/api/salesAnalytics";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getProductImage, useProductImagesStore } from "@/stores/productImages";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import type { ForecastRow, IndustryCode } from "@/types/api";

const DEFAULT_DRIVERS = {
  fashion: [
    { label: "Rainfall", detail: "Above-normal rainfall across key markets", impact: 8, icon: CloudRain },
    { label: "Festival season", detail: "Navratri and Onam demand begins in September", impact: 5, icon: Sparkles },
    { label: "Marketing campaign", detail: "Planned digital campaign adds near-term lift", impact: 3, icon: Megaphone },
    { label: "Historical trend", detail: "Consistent seasonal uplift over the last 3 years", impact: 2, icon: TrendingUp },
  ],
  electronics: [
    { label: "Launch cycle", detail: "New model launches are lifting category demand", impact: 7, icon: Sparkles },
    { label: "Promotion plan", detail: "Marketplace campaign starts next week", impact: 5, icon: Megaphone },
    { label: "Search interest", detail: "Purchase-intent searches are accelerating", impact: 4, icon: TrendingUp },
    { label: "Historical trend", detail: "Seasonal upgrade cycle is repeating", impact: 2, icon: BarChart3 },
  ],
  pharma: [
    { label: "Seasonal incidence", detail: "Prescription demand is rising in key regions", impact: 6, icon: TrendingUp },
    { label: "Institutional orders", detail: "Scheduled hospital demand enters the horizon", impact: 5, icon: ShoppingBag },
    { label: "Safety requirement", detail: "Service-level policy adds a demand buffer", impact: 4, icon: PackageCheck },
    { label: "Historical trend", detail: "Dispensing history shows a recurring increase", impact: 3, icon: BarChart3 },
  ],
  agrocenter: [
    { label: "Rainfall outlook", detail: "Rainfall timing supports near-term input demand", impact: 8, icon: CloudRain },
    { label: "Sowing calendar", detail: "The next planting window is approaching", impact: 5, icon: Sparkles },
    { label: "Dealer activity", detail: "Channel enquiries are increasing", impact: 3, icon: TrendingUp },
    { label: "Historical trend", detail: "Prior seasons show the same demand pattern", impact: 2, icon: BarChart3 },
  ],
  hardware: [
    { label: "Project pipeline", detail: "Confirmed jobs increase near-term demand", impact: 7, icon: ShoppingBag },
    { label: "Supplier pricing", detail: "Price changes are pulling orders forward", impact: 4, icon: CircleDollarSign },
    { label: "Regional demand", detail: "Distributor activity is above baseline", impact: 4, icon: TrendingUp },
    { label: "Historical trend", detail: "The seasonal project cycle is repeating", impact: 3, icon: BarChart3 },
  ],
} satisfies Record<IndustryCode, Array<{ label: string; detail: string; impact: number; icon: AppIcon }>>;

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

function indicativeForecast(
  history: Array<{ date: string; actual: number }>,
  weeks: number,
  demandChangePct: number,
  fallbackBaseline = 100,
): ForecastRow[] {
  if (!history.length) return [];
  const recent = history.slice(-7);
  const recentAverage = recent.reduce((sum, point) => sum + point.actual, 0) / recent.length;
  const baseline = recentAverage > 0 ? recentAverage : fallbackBaseline;
  const start = new Date(history[history.length - 1].date);
  return Array.from({ length: weeks }, (_, index) => {
    const date = new Date(start);
    date.setUTCDate(date.getUTCDate() + (index + 1) * 7);
    const expected = baseline * (1 + (demandChangePct / 100) * ((index + 1) / weeks));
    return {
      sku_id: "portfolio",
      forecast_date: date.toISOString().slice(0, 10),
      p10: expected * 0.9,
      p50: expected,
      p90: expected * 1.1,
    };
  });
}

function SummaryItem({
  icon: Icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: typeof ShoppingBag;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
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
        <p className="mt-0.5 font-mono text-lg font-semibold leading-none text-content">{value}</p>
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
  const history = useQuery({
    queryKey: ["dashboard-history", industry],
    queryFn: () => salesAnalyticsApi.timeseries("day", 30),
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
    queryKey: ["integration-catalog"],
    queryFn: integrationsApi.catalog,
    retry: false,
  });

  const accept = useMutation({
    mutationFn: (id: string) => decisionsApi.accept(id),
    onSuccess: () => {
      toast.success("Recommendation accepted and added to the ROI ledger");
      queryClient.invalidateQueries({ queryKey: ["decisions"] });
      queryClient.invalidateQueries({ queryKey: ["roi-summary"] });
    },
  });

  const response = decisions.data;
  const open = response?.decisions ?? [];
  const primary = open[0];
  const hasDecision = Boolean(primary);
  const totals = response?.totals;
  const portfolioConfidence = confidence.data?.portfolio_confidence ?? primary?.confidence ?? 0;
  const warnings = quality.data?.issues_found ?? 0;
  const stockoutRisk = Math.max(
    totals?.critical ?? 0,
    open.filter((decision) => {
      const cover = decision.inputs?.days_of_cover;
      return typeof cover === "number" && cover <= decision.inputs.lead_time_days;
    }).length,
  );
  const currency = totals?.currency ?? "INR";
  const fmt = (value: number) => formatPrice(value, currency, { compact: true });
  const drivers = DEFAULT_DRIVERS[industry];
  const netChange = drivers.reduce((sum, driver) => sum + driver.impact, 0);
  const historyRows = (history.data?.series ?? []).map((point) => ({ date: point.bucket, actual: point.units_sold }));
  const liveForecastRows = aggregateForecast(forecast.data?.rows ?? []);
  const forecastRows = liveForecastRows.length
    ? liveForecastRows
    : primary
      ? indicativeForecast(
          historyRows,
          12,
          netChange,
          primary.inputs.demand_p50_over_window / Math.max(1, primary.inputs.protection_days / 7),
        )
      : [];
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
  const revenueProtected = primary?.economics?.revenue_protected ?? totals?.revenue_protected ?? 0;
  const suggestedUnits = primary?.recommended_units ?? 0;
  const plannerName = (decoded?.name as string | undefined)?.split(" ")[0] ?? "Sanket";

  return (
    <div className="animate-fade-in space-y-3">
      <header className="flex flex-col gap-3 rounded-2xl border border-line bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-xl font-semibold tracking-tight text-content">
            {hasDecision
              ? `Good morning, ${plannerName} — ${open.length} decision${open.length === 1 ? "" : "s"} need you`
              : `Good morning, ${plannerName} — your planning brief is ready`}
          </h1>
          <p className="mt-0.5 text-sm text-content-muted">
            {hasDecision ? "Here is the most important action to review today." : "No open order decision currently requires approval."}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} />}
          onClick={() => {
            decisions.refetch();
            forecast.refetch();
          }}
          loading={decisions.isFetching || forecast.isFetching}
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
                    {hasDecision ? `Demand expected to increase ${netChange}%` : "Forecast ready. Order decision needs stock context."}
                  </h2>
                  <p className="mt-0.5 text-sm text-content-muted">
                    {hasDecision
                      ? "versus the current plan over the next 12 weeks"
                      : "Sanket will only show an order action after it can support it with auditable inventory and lead-time inputs."}
                  </p>
                </div>
              </div>
              {portfolioConfidence > 0 && (
                <span className="self-start rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                  {portfolioConfidence}% confidence
                </span>
              )}
            </div>

            {hasDecision ? (
              <div className="mt-4 border-t border-line pt-3">
                <div className="mb-2 flex items-center justify-between gap-4">
                  <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-content-subtle">Why this is happening</h3>
                  <span className="text-xs text-content-subtle">Impact on demand</span>
                </div>
                <ol className="space-y-2">
                  {drivers.map(({ label, detail, impact, icon: Icon }) => (
                    <li key={label} className="grid items-center gap-2 sm:grid-cols-[150px_minmax(150px,1fr)_minmax(110px,0.9fr)_44px]">
                      <span className="flex items-center gap-2 text-sm font-semibold text-content"><Icon size={15} className="text-content-muted" />{label}</span>
                      <span className="truncate text-xs text-content-muted">{detail}</span>
                      <span className="h-1.5 overflow-hidden rounded-full bg-surface-3"><span className="block h-full rounded-full bg-[var(--accent)]" style={{ width: `${(impact / drivers[0].impact) * 100}%` }} /></span>
                      <strong className="text-right font-mono text-sm text-content">+{impact}%</strong>
                    </li>
                  ))}
                </ol>
              </div>
            ) : (
              <div className="mt-4 border-t border-line pt-3">
                <div className="flex items-center justify-between gap-4">
                  <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-content-subtle">Decision readiness</h3>
                  <span className="text-xs text-content-subtle">No recommendation invented</span>
                </div>
                <dl className="mt-2 grid gap-2 sm:grid-cols-3">
                  <div className="rounded-xl bg-surface/70 px-3 py-2"><dt className="text-xs text-content-muted">Demand history</dt><dd className="mt-0.5 text-sm font-semibold text-content">{historyRows.length ? "Available" : "Needs data"}</dd></div>
                  <div className="rounded-xl bg-surface/70 px-3 py-2"><dt className="text-xs text-content-muted">Forecast signal</dt><dd className="mt-0.5 text-sm font-semibold text-content">{forecastRows.length ? "Available" : "Needs data"}</dd></div>
                  <div className="rounded-xl bg-surface/70 px-3 py-2"><dt className="text-xs text-content-muted">Order action</dt><dd className="mt-0.5 text-sm font-semibold text-content">None open</dd></div>
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
                    {typeof cover === "number" ? `${cover.toFixed(0)} days cover` : "Coverage pending"} · Service level target: {primary ? `${Math.round(primary.inputs.service_level * 100)}%` : "—"}
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
          </section>

          <section className="rounded-2xl border border-line bg-surface p-4">
            <div className="mb-1 flex items-start justify-between gap-4">
              <div>
                <h2 className="font-heading text-base font-semibold text-content">Forecast snapshot</h2>
                <p className="mt-0.5 text-xs text-content-muted">Thin lines show the expected path; the light band shows the plausible range.</p>
              </div>
              <Link to="/workspace/forecasts" className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--accent)]">Open forecast <ArrowRight size={13} /></Link>
            </div>
            <ForecastChart rows={forecastRows} history={historyRows} height={180} />
          </section>
        </div>

        <aside className="min-w-0 space-y-3">
          <section className="rounded-2xl border border-line bg-surface px-4 py-3">
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-content-muted">Planning summary</h2>
            <div className="mt-1 divide-y divide-line">
              <SummaryItem icon={ShoppingBag} label="Orders due" value={String(totals?.purchase_orders ?? open.length)} detail={`${(totals?.units_to_order ?? 0).toLocaleString()} units`} />
              <SummaryItem icon={PackageCheck} label="Revenue at risk (estimate)" value={fmt(totals?.revenue_protected ?? 0)} detail="covered if the open orders are placed" tone="success" />
              <SummaryItem icon={AlertTriangle} label="Stockout approaching" value={String(stockoutRisk)} detail="SKUs at risk" tone="warning" />
              <SummaryItem icon={TrendingUp} label="Forecast confidence" value={`${portfolioConfidence}%`} detail="portfolio confidence" tone="info" />
              <SummaryItem icon={AlertTriangle} label="Data warnings" value={String(warnings)} detail="need attention" tone={warnings > 0 ? "danger" : "success"} />
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-surface p-3">
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-content-muted">System readiness</h2>
            <dl className="mt-2 grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
              <div className="flex items-center gap-3"><Database size={17} className="text-emerald-600" /><div><dt className="text-xs font-semibold text-content">Data freshness</dt><dd className="text-xs text-content-subtle">{quality.data ? "Audit updated" : "Checking sources"}</dd></div></div>
              <div className="flex items-center gap-3"><Plug size={17} className="text-emerald-600" /><div><dt className="text-xs font-semibold text-content">Integrations</dt><dd className="text-xs text-content-subtle">{integrations.data?.connected ?? 0} connected</dd></div></div>
              <WhatsAppStatus />
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
};
