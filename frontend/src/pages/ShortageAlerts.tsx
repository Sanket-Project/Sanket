import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertOctagon, AlertTriangle, CheckCircle2, Info, Settings, Calendar, RefreshCw, FileSpreadsheet } from "@/components/ui/icons";
import type { AppIcon } from "@/components/ui/icons";
import clsx from "clsx";
import toast from "react-hot-toast";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { shortageAlertsApi } from "@/api/shortageAlerts";
import { decisionsApi, type Decision } from "@/api/decisions";
import { exportApi } from "@/api/export";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { fmtDateTime } from "@/utils/format";
import type { ShortageAlert, AlertSeverity, AlertStatus } from "@/types/api";

const SEVERITY_META: Record<
  AlertSeverity,
  { color: string; icon: AppIcon; bg: string; border: string; glow: string }
> = {
  critical: {
    color: "text-rose-500 dark:text-rose-400",
    bg: "bg-rose-500/5 dark:bg-rose-950/10",
    border: "border-rose-200/50 dark:border-rose-900/30",
    glow: "shadow-rose-500/5",
    icon: AlertOctagon,
  },
  warning: {
    color: "text-amber-500 dark:text-amber-400",
    bg: "bg-amber-500/5 dark:bg-amber-950/10",
    border: "border-amber-200/50 dark:border-amber-900/30",
    glow: "shadow-amber-500/5",
    icon: AlertTriangle,
  },
  info: { 
    color: "text-cyan-500 dark:text-cyan-400", 
    bg: "bg-cyan-500/5 dark:bg-cyan-950/10", 
    border: "border-cyan-200/50 dark:border-cyan-900/30", 
    glow: "shadow-cyan-500/5",
    icon: Info 
  },
};

const STATUS_VARIANT: Record<AlertStatus, "default" | "warning" | "success"> = {
  open: "warning",
  acknowledged: "default",
  resolved: "success",
  suppressed: "default",
};

export const ShortageAlertsPage = () => {
  const industry = useWorkspaceIndustry();
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<AlertStatus | "all">("open");
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | "all">(
    "all",
  );

  const alerts = useQuery({
    queryKey: ["alerts", industry, statusFilter, severityFilter],
    queryFn: () =>
      shortageAlertsApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        severity: severityFilter === "all" ? undefined : severityFilter,
        hours: 168,
        limit: 200,
      }),
    refetchInterval: 60_000,
  });

  const rules = useQuery({
    queryKey: ["alerts", "rules", industry],
    queryFn: () => shortageAlertsApi.listRules(),
  });

  const decisions = useQuery({
    queryKey: ["decisions", industry, "alert-fallback"],
    queryFn: () => decisionsApi.list({ status: "open", limit: 200 }),
  });

  const ack = useMutation({
    mutationFn: (id: string) => shortageAlertsApi.acknowledge(id),
    onSuccess: () => {
      toast.success("Alert acknowledged");
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const resolve = useMutation({
    mutationFn: (id: string) => shortageAlertsApi.resolve(id),
    onSuccess: () => {
      toast.success("Alert resolved");
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const riskDecisions = (decisions.data?.decisions ?? []).filter((decision) =>
    decision.urgency === "critical" ||
    decision.urgency === "high" ||
    (typeof decision.inputs.lead_time_days === "number" &&
      (decision.inputs.days_of_cover ?? Number.POSITIVE_INFINITY) <= decision.inputs.lead_time_days),
  );
  const decisionFallbackActive = (alerts.data?.length ?? 0) === 0 && riskDecisions.length > 0;
  const counts = decisionFallbackActive
    ? {
        critical: riskDecisions.filter((decision) => decision.urgency === "critical").length,
        warning: riskDecisions.filter((decision) => decision.urgency !== "critical").length,
        open: riskDecisions.length,
      }
    : {
        critical: alerts.data?.filter((a) => a.severity === "critical").length ?? 0,
        warning: alerts.data?.filter((a) => a.severity === "warning").length ?? 0,
        open: alerts.data?.filter((a) => a.status === "open").length ?? 0,
      };

  return (
    <div className="space-y-4 animate-fade-in stagger-1" data-industry={industry}>
      {/* ── Page Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-content">
            Stock risks
          </h1>
          <p className="text-sm text-content-subtle mt-1 max-w-2xl leading-relaxed">
            Items likely to run short before the next supplier delivery, with a direct path to the recommended order.
          </p>
        </div>
        <Button
          variant="secondary"
          icon={<FileSpreadsheet size={14} />}
          size="sm"
          className="shrink-0"
          onClick={() => exportApi.alertsCsv(industry ?? "").catch(() => toast.error("Export failed"))}
        >
          Export CSV
        </Button>
      </div>

      {/* ── Summary KPI Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 animate-fade-in stagger-2">
        {[
          {
            label: "Critical Risks",
            count: counts.critical,
            icon: AlertOctagon,
            color: "text-rose-500 dark:text-rose-400",
            bg: "from-rose-500/10 to-transparent",
            border: "border-rose-100 dark:border-rose-950/40",
            sub: "Requires action now"
          },
          {
            label: "Warning Signals",
            count: counts.warning,
            icon: AlertTriangle,
            color: "text-amber-500 dark:text-amber-400",
            bg: "from-amber-500/10 to-transparent",
            border: "border-amber-100 dark:border-amber-950/40",
            sub: "Review this week"
          },
          {
            label: "Active Open Alerts",
            count: counts.open,
            icon: Info,
            color: "text-sky-500 dark:text-sky-400",
            bg: "from-sky-500/10 to-transparent",
            border: "border-sky-100 dark:border-sky-950/40",
            sub: "Awaiting your review"
          }
        ].map(({ label, count, icon: Icon, color, bg, border, sub }) => (
          <Card padding="sm" key={label} className={clsx("relative overflow-hidden group border", border)}>
            <div className={clsx("absolute inset-y-0 left-0 w-1 bg-gradient-to-b", bg)} />
            <div className="flex items-center gap-3.5">
              <div className={clsx("h-10 w-10 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 flex items-center justify-center shadow-inner", color)}>
                <Icon size={20} className="group-hover:scale-110 transition-transform" />
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold tracking-widest text-slate-400 dark:text-slate-500">{label}</div>
                <div className="text-3xl font-extrabold text-slate-800 dark:text-white leading-none mt-0.5 tracking-tight">{count}</div>
              </div>
            </div>
            <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-3 font-medium border-t border-slate-100/50 dark:border-slate-800 pt-2.5">
              {sub}
            </div>
          </Card>
        ))}
      </div>

      {/* ── Filters Section ── */}
      <div className="flex flex-wrap items-center gap-6 px-4 py-3 rounded-xl bg-surface border border-line animate-fade-in stagger-3">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-extrabold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
            Resolution status
          </span>
          <div className="tab-group-container inline-flex">
            {(["all", "open", "acknowledged", "resolved"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s as AlertStatus | "all")}
                className={statusFilter === s ? "tab-item-active capitalize tactile-press" : "tab-item-inactive capitalize tactile-press"}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="hidden md:block w-px h-5 bg-slate-200 dark:bg-slate-800" />

        <div className="flex items-center gap-3">
          <span className="text-[10px] font-extrabold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
            Severity
          </span>
          <div className="tab-group-container inline-flex">
            {(["all", "critical", "warning", "info"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s as AlertSeverity | "all")}
                className={severityFilter === s ? "tab-item-active capitalize tactile-press" : "tab-item-inactive capitalize tactile-press"}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Alert List Deck ── */}
      <div className="space-y-4 animate-fade-in stagger-4">
        {alerts.isPending && (
          <Card className="border-dashed border-2 border-slate-200/80 dark:border-slate-800/80">
            <div className="text-center py-10 flex flex-col items-center justify-center">
              <RefreshCw size={24} className="text-slate-400 animate-spin mb-3" />
              <span className="text-sm font-semibold text-slate-500">Querying active signals database...</span>
            </div>
          </Card>
        )}
        {decisionFallbackActive && riskDecisions.map((decision) => (
          <DecisionRiskRow key={decision.id} decision={decision} />
        ))}
        {alerts.data && alerts.data.length === 0 && !decisionFallbackActive && !decisions.isPending && (
          <Card className="border-dashed border-2 border-slate-200/80 dark:border-slate-800/80 shadow-none">
            <div className="text-center py-8 flex flex-col items-center justify-center max-w-md mx-auto">
              <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-emerald-500/10 to-teal-500/20 flex items-center justify-center mb-4 border border-emerald-500/10 shadow-inner">
                <CheckCircle2 className="text-emerald-500 dark:text-emerald-400" size={24} />
              </div>
              <h3 className="text-base font-bold text-slate-800 dark:text-white mb-1.5">No stock risks need action</h3>
              <p className="text-xs text-slate-400 dark:text-slate-400 leading-relaxed">
                Stock cover is currently ahead of supplier lead times. You can still inspect inventory coverage or review all purchase decisions.
              </p>
              <div className="mt-4 flex items-center justify-center gap-2">
                <Link to="/workspace/inventory"><Button size="sm" variant="secondary">View inventory</Button></Link>
                <Link to="/workspace/decisions"><Button size="sm">Review decisions</Button></Link>
              </div>
            </div>
          </Card>
        )}
        {alerts.data?.map((a) => (
          <AlertRow
            key={a.id}
            alert={a}
            onAck={() => ack.mutate(a.id)}
            onResolve={() => resolve.mutate(a.id)}
          />
        ))}
      </div>

      {/* ── Rule Summary Deck ── */}
      {rules.data && rules.data.length > 0 && (
        <Card
          title={
            <span className="flex items-center gap-2 text-slate-800 dark:text-slate-100 animate-fade-in stagger-5">
              <Settings size={16} className="text-slate-500" />
              Alert thresholds
            </span>
          }
          description="The stock-cover rules currently used to surface risks."
          className="animate-fade-in stagger-5"
        >
          <div className="overflow-x-auto mt-3">
            <table className="w-full text-xs text-slate-600 dark:text-slate-400">
              <thead>
                <tr className="border-b border-slate-200/60 dark:border-slate-800/80 text-slate-400 dark:text-slate-500 uppercase tracking-widest font-extrabold">
                  <th className="text-left py-3 font-extrabold">Rule Scope</th>
                  <th className="text-right py-3 font-extrabold">Warn Threshold</th>
                  <th className="text-right py-3 font-extrabold">Critical Threshold</th>
                  <th className="text-right py-3 font-extrabold">Inventory wt</th>
                  <th className="text-right py-3 font-extrabold">P90 wt</th>
                  <th className="text-right py-3 font-extrabold">Trend wt</th>
                  <th className="text-right py-3 font-extrabold">Cooldown</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-850">
                {rules.data.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/30 dark:hover:bg-slate-900/30 transition-colors">
                    <td className="py-3.5 font-bold text-slate-700 dark:text-slate-200">
                      {r.rule_name}
                    </td>
                    <td className="text-right font-mono font-semibold text-slate-800 dark:text-white">
                      {Number(r.warn_coverage_days).toFixed(0)} Days
                    </td>
                    <td className="text-right font-mono font-semibold text-rose-500 dark:text-rose-400">
                      {Number(r.critical_coverage_days).toFixed(0)} Days
                    </td>
                    <td className="text-right font-mono text-slate-500">
                      {(Number(r.inventory_weight) * 100).toFixed(0)}%
                    </td>
                    <td className="text-right font-mono text-slate-500">
                      {(Number(r.p90_weight) * 100).toFixed(0)}%
                    </td>
                    <td className="text-right font-mono text-slate-500">
                      {(Number(r.trend_weight) * 100).toFixed(0)}%
                    </td>
                    <td className="text-right font-mono font-medium text-slate-400">
                      {r.cooldown_minutes}m
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};

const DecisionRiskRow = ({ decision }: { decision: Decision }) => {
  const cover = decision.inputs.days_of_cover;
  const critical = decision.urgency === "critical";

  return (
    <Card padding="none" className={clsx("overflow-hidden border-l-4", critical ? "border-l-rose-500" : "border-l-amber-500")}>
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={critical ? "danger" : "warning"}>{critical ? "Order now" : "Review this week"}</Badge>
            <span className="font-mono text-xs font-bold text-content-muted">{decision.sku_code ?? decision.sku_id.slice(0, 8)}</span>
            {typeof cover === "number" && (
              <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
                {cover.toFixed(0)} days cover · {decision.inputs.lead_time_days} days lead time
              </span>
            )}
          </div>
          <h3 className="mt-2 font-semibold text-content">{decision.headline}</h3>
          <p className="mt-1 text-sm text-content-subtle">
            {decision.reasons[0]?.text ?? "Current stock is unlikely to cover demand until replenishment arrives."}
          </p>
        </div>
        <Link to="/workspace/decisions" className="shrink-0">
          <Button size="sm">Review order</Button>
        </Link>
      </div>
    </Card>
  );
};

interface RowProps {
  alert: ShortageAlert;
  onAck: () => void;
  onResolve: () => void;
}

const AlertRow = ({ alert, onAck, onResolve }: RowProps) => {
  const meta = SEVERITY_META[alert.severity];
  const Icon = meta.icon;
  return (
    <div
      className={clsx(
        "border rounded-2xl p-5 flex flex-col sm:flex-row items-start justify-between gap-4 card-hover-premium shadow-md shadow-slate-100 dark:shadow-none transition duration-300",
        meta.bg,
        meta.border,
        meta.glow
      )}
    >
      <div className="flex items-start gap-4 flex-1 min-w-0">
        <div className={clsx("h-9 w-9 rounded-xl bg-white/60 dark:bg-black/20 border border-slate-100 dark:border-slate-800/80 flex items-center justify-center shadow-inner shrink-0", meta.color)}>
          <Icon size={18} className="animate-pulse" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2.5 mb-1.5">
            <span
              className={clsx(
                "text-[9px] uppercase tracking-widest font-extrabold px-2 py-0.5 rounded border bg-white/80 dark:bg-slate-900/80 shadow-sm",
                meta.color,
                meta.border
              )}
            >
              {alert.severity}
            </span>
            <Badge variant={STATUS_VARIANT[alert.status]} className="text-[9px] font-extrabold uppercase px-2 shadow-sm">
              {alert.status}
            </Badge>
            <span className="text-[10px] font-bold text-slate-400 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800/50 rounded px-1.5 py-0.5">
              Risk: {(alert.risk_score * 100).toFixed(0)}%
            </span>
            {alert.coverage_days !== null && (
              <span className="text-[10px] font-bold text-slate-400 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800/50 rounded px-1.5 py-0.5">
                {Number(alert.coverage_days).toFixed(1)}d Cover
              </span>
            )}
            {alert.trend_score !== null && (
              <span className="text-[10px] font-bold text-slate-400 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800/50 rounded px-1.5 py-0.5">
                Trend: {Number(alert.trend_score) >= 0 ? "+" : ""}
                {Number(alert.trend_score).toFixed(2)}
              </span>
            )}
          </div>
          <div className="font-bold text-slate-800 dark:text-white text-sm tracking-tight">{alert.title}</div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">{alert.message}</p>
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-400 mt-3.5">
            <Calendar size={11} />
            Fired on {fmtDateTime(alert.fired_at)}
          </div>
        </div>
      </div>
      
      {/* Action buttons */}
      <div className="flex items-center sm:flex-col gap-2 shrink-0 self-end sm:self-center mt-2 sm:mt-0 w-full sm:w-auto border-t border-slate-100 dark:border-slate-800/20 sm:border-0 pt-3 sm:pt-0">
        {alert.status === "open" && (
          <>
            <button
              onClick={onAck}
              className="tactile-press w-full sm:w-28 text-[11px] font-bold px-3 py-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-350 dark:hover:border-slate-700 transition"
            >
              Acknowledge
            </button>
            <button
              onClick={onResolve}
              className="tactile-press w-full sm:w-28 text-[11px] font-bold px-3 py-2 rounded-xl bg-slate-800 text-white hover:bg-slate-700 transition"
            >
              Resolve
            </button>
          </>
        )}
        {alert.status === "acknowledged" && (
          <button
            onClick={onResolve}
            className="tactile-press w-full sm:w-28 text-[11px] font-bold px-3 py-2 rounded-xl bg-slate-800 text-white hover:bg-slate-700 transition shrink-0"
          >
            Resolve
          </button>
        )}
      </div>
    </div>
  );
};
