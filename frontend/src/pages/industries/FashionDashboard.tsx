import { EmptyState } from "@/components/ui/EmptyState";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Shirt, Sparkles, Radio, Boxes } from "@/components/ui/icons";
import { industryApi } from "@/api/industry";
import { forecastsApi } from "@/api/forecasts";
import { useAuthStore } from "@/stores/auth";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { IndustryHero } from "@/components/dashboard/IndustryHero";
import { RankedCategories } from "@/components/dashboard/RankedCategories";
import { fmtCompact } from "@/utils/format";




export const FashionDashboard = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["fashion-overview"],
    queryFn: () => industryApi.overview("fashion"),
  });
  const { data: forecastData } = useQuery({
    queryKey: ["fashion-forecast"],
    queryFn: () => forecastsApi.generate({ horizon: 12 }),
    // Only fire once the auth store has confirmed the user is signed in.
    // Without this guard, the query could run before bootstrap() completes
    // and send an unauthenticated request that triggers the 401 interceptor.
    enabled: isAuthenticated,
    // Forecast errors (e.g. ML service down) should not crash the dashboard;
    // they surface as an empty chart rather than a sign-out.
    retry: false,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <EmptyState title="Industry overview unavailable" description="The source could not be loaded. No business metrics have been inferred." action={<button className="btn-secondary" onClick={() => void refetch()}>Retry overview</button>} />;
  const k = data.kpis;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Hero ── */}
      <IndustryHero
        industry="fashion"
        label="Apparel & Fashion"
        title="Trend & Assortment Intelligence"
        subtitle={`${data.forecast_horizon_weeks}-week horizon · ${data.active_models.length} AI models · Social signal tracking`}
        icon={<Shirt size={26} />}
        horizonWeeks={data.forecast_horizon_weeks}
        models={data.active_models}
      />

      {/* ── Insight Callout ── */}
      <Card title="Signal insight"><p className="text-sm text-content-muted">No verified signal narrative is available from this overview. Review the source before acting.</p><Link to="/workspace/trends" className="mt-3 inline-flex text-sm font-medium text-accent">Review trend evidence</Link></Card>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KPICard
          label="Active SKUs"
          value={k.active_skus == null ? "Unavailable" : fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          subtitle="From the current source report"
          tone="default"
        />
        <KPICard
          label="Validated Trend Signals"
          value={k.validated_signals == null ? "Unavailable" : fmtCompact(k.validated_signals)}
          icon={<Radio size={15} />}
          subtitle="From the current source report"
          tone="success"
        />
        <KPICard
          label="Avg Sell-Through Rate"
          value="Unavailable"
          icon={<Sparkles size={15} />}
          subtitle="From the current source report"
          tone="success"
        />
      </div>

      {/* ── Charts + Categories ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Aggregate Sell-Through Forecast"
          description="Median forecast with 80% prediction interval · Trend-adjusted"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent="var(--chart-forecast)" />
        </Card>

        <Card title="Top Trending Categories" description="Share of active SKU demand">
          <RankedCategories data={(data.top_categories ?? []).map(c => ({ category: c.category, count: c.count }))} />
        </Card>
      </div>

      {/* ── Trend Velocity Panel ── */}
      <Card title="Trend Velocity Signals"><EmptyState variant="subtle" title="Detailed source signals unavailable" description="Signal counts above come from the overview. Open Trend Analysis to inspect available source evidence." action={<Link to="/workspace/trends" className="btn-secondary">Open Trend Analysis</Link>} /></Card>
    </div>
  );
};
