import { EmptyState } from "@/components/ui/EmptyState";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Cpu, AlertTriangle, Boxes, Tag, Clock } from "@/components/ui/icons";
import { industryApi } from "@/api/industry";
import { forecastsApi } from "@/api/forecasts";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { IndustryHero } from "@/components/dashboard/IndustryHero";
import { RankedCategories } from "@/components/dashboard/RankedCategories";
import { fmtCompact } from "@/utils/format";





export const ElectronicsDashboard = () => {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["electronics-overview"],
    queryFn: () => industryApi.overview("electronics"),
  });
  const { data: forecastData } = useQuery({
    queryKey: ["electronics-forecast"],
    queryFn: () => forecastsApi.generate({ horizon: 12 }),
    enabled: true,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <EmptyState title="Industry overview unavailable" description="The source could not be loaded. No business metrics have been inferred." action={<button className="btn-secondary" onClick={() => void refetch()}>Retry overview</button>} />;
  const k = data.kpis;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Hero ── */}
      <IndustryHero
        industry="electronics"
        label="Consumer Electronics"
        title="Component Risk & Demand Sensing"
        subtitle={`${data.forecast_horizon_weeks}-week horizon · Lead-time aware · Real-time supplier signals`}
        icon={<Cpu size={26} />}
        horizonWeeks={data.forecast_horizon_weeks}
        models={data.active_models}
      />

      {/* ── Insight Callout ── */}
      <Card title="Signal insight"><p className="text-sm text-content-muted">No verified signal narrative is available from this overview. Review the source before acting.</p><Link to="/workspace/trends" className="mt-3 inline-flex text-sm font-medium text-accent">Review trend evidence</Link></Card>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Active SKUs"
          value={k.active_skus == null ? "Unavailable" : fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          subtitle="From the current source report"
          tone="default"
        />
        <KPICard
          label="Logistics Disruptions"
          value={k.logistics_disruption_signals == null ? "Unavailable" : fmtCompact(k.logistics_disruption_signals)}
          icon={<AlertTriangle size={15} />}
          subtitle="From the current source report"
          tone={k.logistics_disruption_signals > 5 ? "danger" : "warning"}
        />
        <KPICard
          label="Competitor Price Moves"
          value={k.competitor_price_signals == null ? "Unavailable" : fmtCompact(k.competitor_price_signals)}
          icon={<Tag size={15} />}
          subtitle="From the current source report"
          tone="warning"
        />
        <KPICard
          label="Avg Lead Time"
          value="Unavailable"
          icon={<Clock size={15} />}
          subtitle="From the current source report"
          tone="danger"
        />
      </div>

      {/* ── Charts + Risk Panel ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Demand Forecast"
          description="P10/P50/P90 · Component-risk adjusted · Weekly resolution"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent="var(--chart-forecast)" />
        </Card>

        <Card title="Top Product Categories" description="Active SKU distribution">
          <RankedCategories data={(data.top_categories ?? []).map(c => ({ category: c.category, count: c.count }))} />
        </Card>
      </div>

      {/* ── Component Risk Panel ── */}
      <Card title="Component Risk Radar"><EmptyState variant="subtle" title="Detailed source signals unavailable" description="Signal counts above come from the overview. Open Trend Analysis to inspect available source evidence." action={<Link to="/workspace/trends" className="btn-secondary">Open Trend Analysis</Link>} /></Card>
    </div>
  );
};
