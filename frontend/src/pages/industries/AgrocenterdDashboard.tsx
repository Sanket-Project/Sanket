import { useQuery } from "@tanstack/react-query";
import {
  Sprout,
  CloudRain,
  ShieldCheck,
  Boxes,
  Thermometer,
  TrendingUp,
  DropletIcon,
  Wind,
} from "lucide-react";
import { industryApi } from "@/api/industry";
import { forecastsApi } from "@/api/forecasts";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { IndustryHero } from "@/components/dashboard/IndustryHero";
import { InsightCallout } from "@/components/dashboard/InsightCallout";
import { RankedCategories } from "@/components/dashboard/RankedCategories";
import { fmtCompact } from "@/utils/format";
import { industryAccent } from "@/utils/colors";


const WEATHER_EVENTS = [
  { signal: "La Niña cooling front", category: "Fertilizers", lift: "+18%", icon: <Wind size={13} /> },
  { signal: "Below-avg rainfall (West)", category: "Irrigation Equip.", lift: "+34%", icon: <DropletIcon size={13} /> },
  { signal: "Early frost risk (North)", category: "Crop Protection", lift: "+22%", icon: <Thermometer size={13} /> },
];

const KPI_SPARKS = {
  skus: [420, 435, 430, 448, 455, 462, 471],
  weather: [6, 8, 7, 12, 15, 14, 18],
  regulatory: [3, 4, 3, 4, 3, 5, 4],
  plantingWeek: [1, 2, 3, 5, 7, 8, 8],
};

export const AgrocenterdDashboard = () => {
  const { data, isLoading } = useQuery({
    queryKey: ["agrocenter-overview"],
    queryFn: () => industryApi.overview("agrocenter"),
  });
  const { data: forecastData } = useQuery({
    queryKey: ["agrocenter-forecast"],
    queryFn: () => forecastsApi.generate({ horizon: 26 }),
    enabled: true,
  });

  if (isLoading || !data) return <PageLoader />;
  const k = data.kpis;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Hero ── */}
      <IndustryHero
        industry="agrocenter"
        label="Agrocenter & Farm Inputs"
        title="Seasonal Input Demand Intelligence"
        subtitle={`${data.forecast_horizon_weeks}-week horizon · ${data.active_models.length} AI models active · Weather-adjusted`}
        icon={<Sprout size={26} />}
        horizonWeeks={data.forecast_horizon_weeks}
        models={data.active_models}
        healthScore={76}
        extraBadge={
          <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold">
            <TrendingUp size={10} /> Pre-planting season
          </span>
        }
      />

      {/* ── Insight Callout ── */}
      <InsightCallout
        insight="Demand spike predicted for Fertilizers & Seeds in the next 2 weeks driven by La Niña weather patterns and early planting signals."
        confidence={87}
        category="Weather Signal"
        tone="warning"
        icon={<CloudRain size={18} />}
        ctaLabel="View Forecast"
      />

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Active SKUs"
          value={fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          delta={0.063}
          subtitle="vs. 4-week avg"
          tone="default"
          sparkPoints={KPI_SPARKS.skus}
        />
        <KPICard
          label="Weather Signals"
          value={fmtCompact(k.active_weather_signals)}
          icon={<CloudRain size={15} />}
          delta={0.20}
          subtitle="3 high-impact active"
          tone="warning"
          sparkPoints={KPI_SPARKS.weather}
        />
        <KPICard
          label="Regulatory Alerts"
          value={fmtCompact(k.validated_regulatory_signals)}
          icon={<ShieldCheck size={15} />}
          delta={-0.05}
          subtitle="Stable this week"
          tone="default"
          sparkPoints={KPI_SPARKS.regulatory}
        />
        <KPICard
          label="Planting Season"
          value="Week 6"
          icon={<Sprout size={15} />}
          subtitle="Peak demand window"
          tone="success"
          sparkPoints={KPI_SPARKS.plantingWeek}
        />
      </div>

      {/* ── Charts + Categories ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Seasonal Demand Forecast"
          description="80% prediction interval · Pre-planting peak visible in weeks 6–10"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent={industryAccent.agrocenter} />
        </Card>

        <Card title="Top Input Categories" description="Share of active product count">
          <RankedCategories data={(data.top_categories ?? []).map(c => ({ category: c.category, count: c.count }))} />
        </Card>
      </div>

      {/* ── Weather Impact Panel ── */}
      <Card
        title="Active Weather Impact Signals"
        description="Signal → Affected Category → Demand Lift estimate"
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {WEATHER_EVENTS.map((ev) => (
            <div
              key={ev.signal}
              className="flex items-start gap-3 p-3.5 rounded-xl bg-amber-50/60 border border-amber-200/70 dark:bg-amber-900/15 dark:border-amber-700/30"
            >
              <div className="h-8 w-8 rounded-lg bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
                {ev.icon}
              </div>
              <div className="min-w-0">
                <p className="text-[13px] font-semibold text-content leading-snug truncate">{ev.signal}</p>
                <p className="text-xs text-content-subtle mt-0.5 truncate">{ev.category}</p>
                <span className="inline-block mt-1.5 font-mono text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/15 px-1.5 py-0.5 rounded-md tabular-figs">
                  Demand {ev.lift}
                </span>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
