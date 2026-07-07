import { useQuery } from "@tanstack/react-query";
import {
  Cpu,
  AlertTriangle,
  Boxes,
  Tag,
  Clock,
  Package,
  ShipIcon,
} from "lucide-react";
import { industryApi } from "@/api/industry";
import { forecastsApi } from "@/api/forecasts";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { IndustryHero } from "@/components/dashboard/IndustryHero";
import { InsightCallout } from "@/components/dashboard/InsightCallout";
import { RankedCategories } from "@/components/dashboard/RankedCategories";
import { fmtCompact } from "@/utils/format";
import { industryAccent } from "@/utils/colors";


const RISK_SIGNALS = [
  {
    component: "TSMC 5nm Chips",
    risk: "High",
    leadTime: "18 weeks",
    tone: "danger" as const,
  },
  {
    component: "Samsung OLED Panels",
    risk: "Medium",
    leadTime: "10 weeks",
    tone: "warning" as const,
  },
  {
    component: "Lithium Battery Cells",
    risk: "Medium",
    leadTime: "8 weeks",
    tone: "warning" as const,
  },
  {
    component: "Bosch MEMS Sensors",
    risk: "Low",
    leadTime: "4 weeks",
    tone: "success" as const,
  },
];

const KPI_SPARKS = {
  skus: [1120, 1145, 1138, 1160, 1175, 1182, 1198],
  disruptions: [4, 5, 7, 9, 8, 11, 12],
  price: [18, 21, 19, 24, 22, 26, 28],
  leadTime: [12, 13, 14, 16, 15, 17, 18],
};

const RISK_BADGE: Record<string, "danger" | "warning" | "success"> = {
  High: "danger",
  Medium: "warning",
  Low: "success",
};

export const ElectronicsDashboard = () => {
  const { data, isLoading } = useQuery({
    queryKey: ["electronics-overview"],
    queryFn: () => industryApi.overview("electronics"),
  });
  const { data: forecastData } = useQuery({
    queryKey: ["electronics-forecast"],
    queryFn: () => forecastsApi.generate({ horizon: 12 }),
    enabled: true,
  });

  if (isLoading || !data) return <PageLoader />;
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
        healthScore={68}
        extraBadge={
          <span className="flex items-center gap-1 text-rose-500 font-semibold">
            <AlertTriangle size={10} /> 3 supply risks
          </span>
        }
      />

      {/* ── Insight Callout ── */}
      <InsightCallout
        insight="TSMC 5nm chip shortage may constrain Smartphone production by 23% in Q3 — consider forward purchasing within 2 weeks."
        confidence={82}
        category="Supply Chain Risk"
        tone="danger"
        icon={<ShipIcon size={18} />}
        ctaLabel="View Risk Details"
      />

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Active SKUs"
          value={fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          delta={0.042}
          subtitle="vs. prior month"
          tone="default"
          sparkPoints={KPI_SPARKS.skus}
        />
        <KPICard
          label="Logistics Disruptions"
          value={fmtCompact(k.logistics_disruption_signals)}
          icon={<AlertTriangle size={15} />}
          delta={0.18}
          subtitle="3 high-severity active"
          tone={k.logistics_disruption_signals > 5 ? "danger" : "warning"}
          sparkPoints={KPI_SPARKS.disruptions}
        />
        <KPICard
          label="Competitor Price Moves"
          value={fmtCompact(k.competitor_price_signals)}
          icon={<Tag size={15} />}
          delta={0.12}
          subtitle="Last 7 days"
          tone="warning"
          sparkPoints={KPI_SPARKS.price}
        />
        <KPICard
          label="Avg Lead Time"
          value="18 wks"
          icon={<Clock size={15} />}
          delta={0.09}
          subtitle="+2wk vs. Q1 avg"
          tone="danger"
          sparkPoints={KPI_SPARKS.leadTime}
        />
      </div>

      {/* ── Charts + Risk Panel ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Demand Forecast"
          description="P10/P50/P90 · Component-risk adjusted · Weekly resolution"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent={industryAccent.electronics} />
        </Card>

        <Card title="Top Product Categories" description="Active SKU distribution">
          <RankedCategories data={(data.top_categories ?? []).map(c => ({ category: c.category, count: c.count }))} />
        </Card>
      </div>

      {/* ── Component Risk Panel ── */}
      <Card
        title="Component Risk Radar"
        description="Critical supply components · Risk level · Estimated lead time"
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {RISK_SIGNALS.map((r) => (
            <div
              key={r.component}
              className="flex flex-col gap-2 p-3.5 rounded-xl border border-line bg-surface-2"
            >
              <div className="flex items-center justify-between">
                <div className="h-8 w-8 rounded-lg bg-surface-3 text-content-muted grid place-items-center">
                  <Package size={15} />
                </div>
                <Badge variant={RISK_BADGE[r.risk]}>{r.risk} Risk</Badge>
              </div>
              <div>
                <p className="text-[13px] font-semibold text-content leading-snug">{r.component}</p>
                <div className="flex items-center gap-1 mt-1 text-xs text-content-subtle tabular-figs">
                  <Clock size={12} />
                  <span>Lead time: {r.leadTime}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
