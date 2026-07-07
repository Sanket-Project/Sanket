import { useQuery } from "@tanstack/react-query";
import {
  Shirt,
  Sparkles,
  Radio,
  Boxes,
  Flame,
  Heart,
  Star,
  TrendingUp,
} from "lucide-react";
import { industryApi } from "@/api/industry";
import { forecastsApi } from "@/api/forecasts";
import { useAuthStore } from "@/stores/auth";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { IndustryHero } from "@/components/dashboard/IndustryHero";
import { InsightCallout } from "@/components/dashboard/InsightCallout";
import { RankedCategories } from "@/components/dashboard/RankedCategories";
import { fmtCompact } from "@/utils/format";
import { industryAccent } from "@/utils/colors";


const TREND_SIGNALS = [
  {
    signal: "Quiet Luxury Aesthetic",
    source: "Instagram + TikTok",
    sentiment: 94,
    velocity: "+31%",
    icon: <Star size={13} />,
  },
  {
    signal: "Y2K Revival — Denim",
    source: "Pinterest + Runway",
    sentiment: 88,
    velocity: "+27%",
    icon: <Flame size={13} />,
  },
  {
    signal: "Sustainable Fabrics",
    source: "Google Search + Press",
    sentiment: 76,
    velocity: "+19%",
    icon: <Heart size={13} />,
  },
];

const KPI_SPARKS = {
  skus: [2100, 2140, 2155, 2178, 2190, 2215, 2242],
  signals: [38, 42, 47, 53, 58, 64, 71],
  sellThrough: [62, 65, 67, 70, 68, 72, 74],
};

export const FashionDashboard = () => {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data, isLoading } = useQuery({
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

  if (isLoading || !data) return <PageLoader />;
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
        healthScore={84}
        extraBadge={
          <span className="flex items-center gap-1 text-pink-600 dark:text-pink-400 font-semibold">
            <TrendingUp size={10} /> SS26 season active
          </span>
        }
      />

      {/* ── Insight Callout ── */}
      <InsightCallout
        insight="'Quiet Luxury' trend surging across Instagram & TikTok — 31% demand velocity increase for neutral-toned Women's Apparel predicted in next 3 weeks."
        confidence={91}
        category="Trend Signal"
        tone="success"
        icon={<Sparkles size={18} />}
        ctaLabel="View Trend Details"
      />

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KPICard
          label="Active SKUs"
          value={fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          delta={0.084}
          subtitle="vs. prior season"
          tone="default"
          sparkPoints={KPI_SPARKS.skus}
        />
        <KPICard
          label="Validated Trend Signals"
          value={fmtCompact(k.validated_signals)}
          icon={<Radio size={15} />}
          delta={0.318}
          subtitle="3 new this week"
          tone="success"
          sparkPoints={KPI_SPARKS.signals}
        />
        <KPICard
          label="Avg Sell-Through Rate"
          value="74%"
          icon={<Sparkles size={15} />}
          delta={0.06}
          subtitle="+6% vs. SS25 season"
          tone="success"
          sparkPoints={KPI_SPARKS.sellThrough}
        />
      </div>

      {/* ── Charts + Categories ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Aggregate Sell-Through Forecast"
          description="Median forecast with 80% prediction interval · Trend-adjusted"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent={industryAccent.fashion} />
        </Card>

        <Card title="Top Trending Categories" description="Share of active SKU demand">
          <RankedCategories data={(data.top_categories ?? []).map(c => ({ category: c.category, count: c.count }))} />
        </Card>
      </div>

      {/* ── Trend Velocity Panel ── */}
      <Card
        title="Trend Velocity Signals"
        description="Real-time social & market trend signals · Sentiment score · Week-over-week velocity"
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {TREND_SIGNALS.map((tr) => (
            <div
              key={tr.signal}
              className="flex flex-col gap-3 p-4 rounded-xl border border-line bg-surface-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div
                  className="h-8 w-8 rounded-lg grid place-items-center shrink-0"
                  style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                >
                  {tr.icon}
                </div>
                <span className="font-mono text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/15 px-1.5 py-0.5 rounded-md tabular-figs">
                  {tr.velocity}
                </span>
              </div>
              <div>
                <p className="text-[13px] font-semibold text-content leading-snug">{tr.signal}</p>
                <p className="text-xs text-content-subtle mt-0.5">{tr.source}</p>
              </div>
              {/* Sentiment bar */}
              <div>
                <div className="flex items-center justify-between text-[11px] font-medium text-content-muted mb-1 tabular-figs">
                  <span>Sentiment</span>
                  <span>{tr.sentiment}%</span>
                </div>
                <div className="h-2 rounded-full bg-surface-3 overflow-hidden">
                  <div
                    className="h-2 rounded-full transition-all duration-700"
                    style={{ width: `${tr.sentiment}%`, background: "var(--accent)" }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
