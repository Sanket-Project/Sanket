import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Eye,
  Info,
  PlugZap,
  RefreshCw,
  Sparkles,
  Wrench,
} from "@/components/ui/icons";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageLoader } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useIndustryStore } from "@/stores/industry";
import { getErrorMessage } from "@/utils/errors";
import {
  dataQualityApi,
  type DataQualityFinding,
  type DataQualityFix,
  type DataQualitySeverity,
} from "@/api/dataQuality";

const SEVERITY: Record<DataQualitySeverity, { variant: "danger" | "warning" | "info"; label: string }> = {
  critical: { variant: "danger", label: "Critical" },
  warning: { variant: "warning", label: "Warning" },
  info: { variant: "info", label: "Note" },
};

function scoreTone(score: number) {
  if (score >= 90) return "text-emerald-600";
  if (score >= 70) return "text-cyan-600";
  if (score >= 40) return "text-amber-600";
  return "text-rose-600";
}

/**
 * Dataset health.
 *
 * The boring feature that decides whether every other feature works. Each
 * finding says what is wrong, why it matters *for forecasting* (not in the
 * abstract), and shows real affected rows so the user can go and look.
 * Auto-fixes always preview the row count before anything is deleted.
 */
export const DataQualityPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [pendingFix, setPendingFix] = useState<{ action: DataQualityFix; rows: number; label: string } | null>(null);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["data-quality", industry],
    queryFn: dataQualityApi.report,
  });

  const preview = useMutation({
    mutationFn: ({ action }: { action: DataQualityFix; label: string }) =>
      dataQualityApi.fix(action, false),
    onSuccess: (res, vars) => {
      if (res.rows_affected === 0) {
        toast.success("Nothing left to fix here");
        refetch();
        return;
      }
      setPendingFix({ action: res.action, rows: res.rows_affected, label: vars.label });
    },
    onError: (e) => toast.error(getErrorMessage(e)),
  });

  const apply = useMutation({
    mutationFn: (action: DataQualityFix) => dataQualityApi.fix(action, true),
    onSuccess: (res) => {
      setPendingFix(null);
      queryClient.invalidateQueries({ queryKey: ["data-quality"] });
      toast.success(`Removed ${res.rows_affected.toLocaleString()} row(s)`);
    },
    onError: (e) => {
      setPendingFix(null);
      toast.error(getErrorMessage(e));
    },
  });

  if (isLoading || !data) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-cyan-600">
            <Sparkles size={14} /> Data quality
          </div>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Is your data good enough?</h1>
          <p className="mt-1 max-w-2xl text-content-subtle">
            Bad data beats good algorithms every time. These checks run over your whole dataset and
            tell you what to fix first.
          </p>
        </div>
        <Button
          variant="secondary"
          icon={<RefreshCw size={15} />}
          loading={isFetching}
          onClick={() => refetch()}
        >
          Re-run checks
        </Button>
      </div>

      <Card padding="none">
        <div className="grid divide-y divide-line sm:grid-cols-[minmax(210px,1.2fr)_repeat(3,minmax(110px,0.7fr))] sm:divide-x sm:divide-y-0">
          <div className="flex items-center gap-4 px-5 py-4">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-widest text-content-subtle">
                Dataset health
              </p>
              <p className={`mt-1 font-heading text-4xl font-bold tabular-nums ${scoreTone(data.health_score)}`}>
                {data.health_score}
              </p>
            </div>
            <div className="min-w-0 border-l border-line pl-4">
              <p className="text-sm font-semibold text-content">{data.grade}</p>
              <p className="mt-1 text-xs leading-relaxed text-content-subtle">
                {data.checks_run} checks · {data.issues_found} issue
                {data.issues_found === 1 ? "" : "s"}
              </p>
            </div>
          </div>
          <Stat label="Critical" value={data.critical} tone={data.critical > 0 ? "danger" : "ok"} />
          <Stat label="Warnings" value={data.warnings} tone={data.warnings > 0 ? "warn" : "ok"} />
          <Stat
            label="Auto-fixable"
            value={data.fixable_automatically.length}
            tone={data.fixable_automatically.length > 0 ? "warn" : "ok"}
          />
        </div>
      </Card>

      {data.findings.length === 0 ? (
        <Card padding="none">
          <EmptyState
            icon={<CheckCircle2 size={22} />}
            title="Every check passed"
            description="No duplicates, no gaps, no missing economics, no stale stock. Your forecasts are running on clean inputs."
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {data.findings.map((f) => (
            <FindingCard
              key={f.key}
              finding={f}
              expanded={open === f.key}
              onToggle={() => setOpen(open === f.key ? null : f.key)}
              onFix={() =>
                f.autofix && preview.mutate({ action: f.autofix, label: f.label })
              }
              onRerun={() => refetch()}
              fixing={preview.isPending}
              rerunning={isFetching}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingFix !== null}
        onClose={() => setPendingFix(null)}
        onConfirm={() => pendingFix && apply.mutate(pendingFix.action)}
        title={`Delete ${pendingFix?.rows.toLocaleString() ?? 0} rows?`}
        message={
          `"${pendingFix?.label ?? ""}" — ${pendingFix?.rows.toLocaleString() ?? 0} row(s) will be ` +
          "permanently removed from your sales history. This cannot be undone; re-import the file " +
          "if you need them back."
        }
        confirmLabel="Delete rows"
        tone="danger"
        loading={apply.isPending}
      />
    </div>
  );
};

function Stat({ label, value, tone }: { label: string; value: number; tone: "ok" | "warn" | "danger" }) {
  const color = { ok: "text-emerald-600", warn: "text-amber-600", danger: "text-rose-600" }[tone];
  return (
    <div className="flex min-h-[82px] flex-col justify-center px-5 py-4">
      <p className="text-[11px] font-bold uppercase tracking-widest text-content-subtle">{label}</p>
      <p className={`mt-1 font-heading text-2xl font-bold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function FindingCard({
  finding: f,
  expanded,
  onToggle,
  onFix,
  onRerun,
  fixing,
  rerunning,
}: {
  finding: DataQualityFinding;
  expanded: boolean;
  onToggle: () => void;
  onFix: () => void;
  onRerun: () => void;
  fixing: boolean;
  rerunning: boolean;
}) {
  const sev = SEVERITY[f.severity];
  const isInventoryIssue = f.key === "no_inventory_record" || f.key === "stale_inventory";
  return (
    <Card padding="none">
      <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-[15px] font-semibold text-content">{f.label}</h3>
            <Badge variant={sev.variant} dot>
              {sev.label}
            </Badge>
            {f.count > 0 && (
              <span className="font-mono text-xs font-semibold text-content-muted">
                {f.count.toLocaleString()}
              </span>
            )}
          </div>

          <p className="mt-2 flex gap-2 text-sm leading-relaxed text-content-muted">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-content-subtle" />
            {f.why_it_matters}
          </p>
          <p className="mt-1.5 flex gap-2 text-sm leading-relaxed text-content-muted">
            <Wrench size={14} className="mt-0.5 shrink-0 text-content-subtle" />
            {f.how_to_fix}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2 lg:max-w-[360px] lg:justify-end">
          {f.autofix ? (
            <Button size="sm" loading={fixing} onClick={onFix}>
              Review auto-fix
            </Button>
          ) : isInventoryIssue ? (
            <Link
              to="/workspace/integrations"
              className="btn-primary px-3 py-1.5 text-xs"
            >
              <PlugZap size={14} aria-hidden="true" />
              Reconnect inventory
            </Link>
          ) : null}

          {f.sample.length > 0 && (
            <Button
              size="sm"
              variant="secondary"
              icon={expanded ? <ChevronDown size={14} /> : <Eye size={14} />}
              onClick={onToggle}
            >
              {expanded ? "Hide rows" : "Review rows"}
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw size={14} />}
            loading={rerunning}
            onClick={onRerun}
          >
            Re-run
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-line bg-surface-2/60 px-5 py-4">
          {f.sample.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-content-subtle">
              <Info size={14} /> No specific rows to show for this check.
            </p>
          ) : (
            <>
              <p className="mb-3 text-xs font-bold uppercase tracking-widest text-content-subtle">
                Affected rows (first {f.sample.length})
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-left">
                      {Object.keys(f.sample[0]).map((k) => (
                        <th
                          key={k}
                          className="whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-content-subtle"
                        >
                          {k.replace(/_/g, " ")}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {f.sample.map((row, i) => (
                      <tr key={i} className="border-b border-line/60 last:border-0">
                        {Object.values(row).map((v, j) => (
                          <td
                            key={j}
                            className="max-w-xs truncate px-3 py-2 font-mono text-xs text-content-muted"
                          >
                            {v === null || v === undefined
                              ? "—"
                              : typeof v === "object"
                                ? JSON.stringify(v)
                                : String(v)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
