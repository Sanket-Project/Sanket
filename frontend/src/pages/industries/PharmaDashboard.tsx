import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Pill,
  ShieldCheck,
  AlertTriangle,
  Boxes,
  FileCheck2,
  CheckCircle2,
  Clock,
  XCircle,
} from "lucide-react";
import { industryApi } from "@/api/industry";
import { forecastsApi } from "@/api/forecasts";
import { pharmaApi } from "@/api/pharma";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { IndustryHero } from "@/components/dashboard/IndustryHero";
import { InsightCallout } from "@/components/dashboard/InsightCallout";
import { ExpiryTimeline } from "@/components/dashboard/ExpiryTimeline";
import { fmtCompact } from "@/utils/format";
import { industryAccent } from "@/utils/colors";
import type { PharmaBatchExpiring } from "@/types/api";

function daysUntil(isoDate: string): number {
  const ms = new Date(isoDate).getTime() - Date.now();
  return Math.max(0, Math.round(ms / 86_400_000));
}

/** Build the expiry insight from real batch data instead of hardcoded copy. */
function buildExpiryInsight(batches: PharmaBatchExpiring[]): {
  message: string;
  tone: "danger" | "warning" | "success";
} {
  if (batches.length === 0) {
    return {
      message: "No released batches are expiring within the next 90 days — shelf-life risk is currently low.",
      tone: "success",
    };
  }
  const urgent = batches.slice(0, 2);
  const lotList = urgent.map((b) => b.lot_number).join(" & ");
  const days = urgent.map((b) => daysUntil(b.expiry_date));
  const dayRange =
    Math.min(...days) === Math.max(...days)
      ? `${Math.min(...days)} days`
      : `${Math.min(...days)}–${Math.max(...days)} days`;
  const anyColdChain = urgent.some((b) => b.cold_chain_required);
  const critical = batches.filter((b) => daysUntil(b.expiry_date) <= 30).length;
  const suffix = critical > 0 ? ` ${critical} lot${critical !== 1 ? "s" : ""} need${critical === 1 ? "s" : ""} immediate action.` : "";
  return {
    message: `${batches.length} batch${batches.length !== 1 ? "es" : ""} (${lotList}${batches.length > 2 ? ", +" + (batches.length - 2) + " more" : ""}) expire within ${dayRange}${anyColdChain ? " with cold-chain requirements" : ""}.${suffix}`,
    tone: critical > 0 ? "danger" : "warning",
  };
}

export const PharmaDashboard = () => {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["pharma-overview"],
    queryFn: () => industryApi.overview("pharma"),
  });
  const { data: expiring } = useQuery({
    queryKey: ["pharma-expiring", 90],
    queryFn: () => pharmaApi.expiringBatches(90),
  });
  const { data: forecastData } = useQuery({
    queryKey: ["pharma-forecast"],
    queryFn: () => forecastsApi.generate({ horizon: 16 }),
    enabled: true,
  });

  if (isLoading || !data) return <PageLoader />;
  const k = data.kpis;

  const expiryBatches = expiring?.batches ?? [];
  const expiryCount = expiring?.count ?? 0;
  const insight = buildExpiryInsight(expiryBatches);
  const criticalExpiring = k.batches_expiring_critical_30_days ?? 0;

  const totalBatches = k.batches_total ?? 0;
  const compliancePct = (count: number) =>
    totalBatches > 0 ? Math.round((count / totalBatches) * 100) : 0;
  const complianceStats = [
    {
      label: "Released",
      value: compliancePct(k.batches_released ?? 0),
      color: "#10b981",
      bg: "bg-emerald-50 dark:bg-emerald-900/20",
      border: "border-emerald-200/70 dark:border-emerald-800/40",
      icon: <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400" />,
    },
    {
      label: "Quarantine",
      value: compliancePct(k.batches_in_quarantine ?? 0),
      color: "#f59e0b",
      bg: "bg-amber-50 dark:bg-amber-900/20",
      border: "border-amber-200/70 dark:border-amber-800/40",
      icon: <Clock size={16} className="text-amber-600 dark:text-amber-400" />,
    },
    {
      label: "Rejected / Recalled / Expired",
      value: compliancePct(k.batches_non_conforming ?? 0),
      color: "#ef4444",
      bg: "bg-rose-50 dark:bg-rose-900/20",
      border: "border-rose-200/70 dark:border-rose-800/40",
      icon: <XCircle size={16} className="text-rose-600 dark:text-rose-400" />,
    },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Hero ── */}
      <IndustryHero
        industry="pharma"
        label="Pharmaceuticals"
        title="GxP-Compliant Demand & Batch Intelligence"
        subtitle={`${data.forecast_horizon_weeks}-week horizon · Audit-trailed · FDA 21 CFR Part 11 compliant`}
        icon={<Pill size={26} />}
        horizonWeeks={data.forecast_horizon_weeks}
        models={data.active_models}
        healthScore={91}
        extraBadge={
          <span className="flex items-center gap-1 text-emerald-700 dark:text-emerald-400 font-semibold">
            <ShieldCheck size={10} /> GxP Audit Active
          </span>
        }
      />

      {/* ── Insight Callout ── */}
      <InsightCallout
        insight={insight.message}
        confidence={expiryBatches.length > 0 ? 96 : 100}
        category="Batch Expiry"
        tone={insight.tone}
        icon={<AlertTriangle size={18} />}
        ctaLabel="View Expiry Plan"
        onCta={() => navigate("/workspace/pharma/batches")}
      />

      {/* ── KPI Cards (5-column) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <KPICard
          label="Active SKUs"
          value={fmtCompact(k.active_skus)}
          icon={<Boxes size={15} />}
          subtitle="Manufacturing active"
          tone="default"
        />
        <KPICard
          label="Batches Released"
          value={fmtCompact(k.batches_released)}
          icon={<ShieldCheck size={15} />}
          subtitle="QA-approved"
          tone="success"
        />
        <KPICard
          label="In Quarantine"
          value={fmtCompact(k.batches_in_quarantine)}
          icon={<FileCheck2 size={15} />}
          subtitle="Pending QA review"
          tone="warning"
        />
        <KPICard
          label="Expiring ≤ 90d"
          value={fmtCompact(k.batches_expiring_in_90_days)}
          icon={<AlertTriangle size={15} />}
          subtitle={`${criticalExpiring} critical (<30d)`}
          tone={k.batches_expiring_in_90_days > 10 ? "danger" : criticalExpiring > 0 ? "warning" : "default"}
        />
        <KPICard
          label="Regulatory Signals"
          value={fmtCompact(k.active_regulatory_signals)}
          icon={<ShieldCheck size={15} />}
          subtitle="FDA & EMA monitoring"
          tone="default"
        />
      </div>

      {/* ── Forecast + Expiry Timeline ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title="Demand Forecast — Croston + TFT Blend"
          description="Intermittent-demand aware · 52-week horizon · Audit-trailed"
        >
          <ForecastChart rows={forecastData?.rows ?? []} accent={industryAccent.pharma} />
        </Card>

        <Card
          title="Expiry Timeline"
          description="Batches within 90 days · Urgency-ranked"
        >
          <ExpiryTimeline batches={expiryBatches} count={expiryCount} />
        </Card>
      </div>

      {/* ── Compliance Snapshot ── */}
      <Card
        title="Batch Compliance Snapshot"
        description="Current batch status distribution across the manufacturing pipeline"
      >
        {totalBatches === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm font-semibold text-content-muted">No batch data yet</p>
            <p className="text-xs text-content-subtle mt-1">
              Import batch records (lot numbers, GxP status, expiry dates) to populate this snapshot.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {complianceStats.map((stat) => (
              <div
                key={stat.label}
                className={`flex items-center gap-4 p-4 rounded-xl border ${stat.bg} ${stat.border}`}
              >
                <div className="h-11 w-11 rounded-xl bg-surface grid place-items-center shadow-sm shrink-0">
                  {stat.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-2xl font-semibold text-content tabular-figs">{stat.value}%</div>
                  <div className="text-xs font-semibold text-content-muted">{stat.label}</div>
                  <div className="h-1.5 mt-2 rounded-full bg-surface-3 overflow-hidden">
                    <div
                      className="h-1.5 rounded-full transition-all duration-700"
                      style={{ width: `${stat.value}%`, background: stat.color }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
