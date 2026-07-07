import { useQuery } from "@tanstack/react-query";
import {
  Wrench,
  Truck,
  Boxes,
  Tag,
  TrendingUp,
  PackageCheck,
  Timer,
  AlertTriangle,
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


const SUPPLY_EVENTS = [
  { signal: "Container rates up 14% (Asia–EU)", category: "Power Tools", lift: "+11 days", icon: <Truck size={13} /> },
  { signal: "Steel index +6% MoM", category: "Fasteners", lift: "+4% cost", icon: <TrendingUp size={13} /> },
  { signal: "Copper supplier lead-time slip", category: "Electrical", lift: "+9 days", icon: <Timer size={13} /> },
];

const KPI_SPARKS = {
  skus: [180, 188, 192, 199, 205, 210, 214],
  price: [4, 5, 5, 7, 9, 8, 11],
  supply: [2, 3, 3, 4, 5, 6, 6],
  fill: [91, 92, 90, 93, 94, 93, 95],
};

export const HardwareDashboard = () => {
  const { data, isLoading } = useQuery({
    queryKey: ["hardware-overview"],
    queryFn: () => industryApi.overview("hardware"),
  });
  const { data: forecastData } = useQuery({
    queryKey: ["hardware-forecast"],
    queryFn: () => forecastsApi.generate({ horizon: 16 }),
    enabled: true,
  });

  if (isLoading || !data) return <PageLoader />;
  const k = data.kpis;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Hero ── */}
      <IndustryHero
        industry="hardware"
        label="Hardware & Industrial Supply"
        title="Lead-Time & Replenishment Intelligence"
        subtitle={`${data.forecast_horizon_weeks}-week horizon · ${data.active_models.length} AI models active · Supply-chain aware`}
        icon={<Wrench size={26} />}
        horizonWeeks={data.forecast_horizon_weeks}
        models={data.active_models}
        healthScore={82}
        extraBadge={
          <span className="flex items-center gap-1 text-orange-600 dark:text-orange-400 font-semibold">
            <TrendingUp size={10} /> Project season
          </span>
        }
      />

      {/* ── Insight Callout ── */}
      <InsightCallout
        insight="Rising container freight rates and a steel-index uptick are pushing fastener and power-tool lead times out by 1–2 weeks. Pre-build safety stock on long-lead SKUs."
        confidence={84}
        category="Supply Signal"
        tone="warning"
        icon={<Truck size={18} />}
        ctaLabel="View Forecast"
      />

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Active SKUs"
          value={fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          delta={0.045}
          subtitle="vs. 4-week avg"
          tone="default"
          sparkPoints={KPI_SPARKS.skus}
        />
        <KPICard
          label="Price Signals"
          value={fmtCompact(k.active_price_signals)}
          icon={<Tag size={15} />}
          delta={0.18}
          subtitle="Commodity & competitor"
          tone="warning"
          sparkPoints={KPI_SPARKS.price}
        />
        <KPICard
          label="Supply Alerts"
          value={fmtCompact(k.validated_supply_signals)}
          icon={<AlertTriangle size={15} />}
          delta={0.12}
          subtitle="Lead-time / logistics"
          tone="warning"
          sparkPoints={KPI_SPARKS.supply}
        />
        <KPICard
          label="Fill Rate"
          value="95%"
          icon={<PackageCheck size={15} />}
          subtitle="On-shelf availability"
          tone="success"
          sparkPoints={KPI_SPARKS.fill}
        />
      </div>

      {/* ── Charts + Categories ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Demand Forecast"
          description="80% prediction interval · Steady industrial demand with project-season ramp"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent={industryAccent.hardware} />
        </Card>

        <Card title="Top Categories" description="Share of active product count">
          <RankedCategories data={(data.top_categories ?? []).map(c => ({ category: c.category, count: c.count }))} />
        </Card>
      </div>

      {/* ── Supply-Chain Impact Panel ── */}
      <Card
        title="Active Supply-Chain Signals"
        description="Signal → Affected Category → Lead-time / Cost impact"
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {SUPPLY_EVENTS.map((ev) => (
            <div
              key={ev.signal}
              className="flex items-start gap-3 p-3.5 rounded-xl bg-orange-50/60 border border-orange-200/70 dark:bg-orange-900/15 dark:border-orange-700/30"
            >
              <div className="h-8 w-8 rounded-lg bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400 flex items-center justify-center shrink-0">
                {ev.icon}
              </div>
              <div className="min-w-0">
                <p className="text-[13px] font-semibold text-content leading-snug truncate">{ev.signal}</p>
                <p className="text-xs text-content-subtle mt-0.5 truncate">{ev.category}</p>
                <span className="inline-block mt-1.5 font-mono text-[11px] font-semibold text-orange-700 dark:text-orange-400 bg-orange-50 dark:bg-orange-500/15 px-1.5 py-0.5 rounded-md tabular-figs">
                  Impact {ev.lift}
                </span>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
