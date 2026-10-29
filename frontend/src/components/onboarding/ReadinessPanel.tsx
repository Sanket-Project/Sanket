import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarCheck, Check, CircleDashed, Lock } from "@/components/ui/icons";
import clsx from "clsx";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { readinessApi, type ReadinessMilestone } from "@/api/onboarding";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";

/**
 * The seven-day plan.
 *
 * "Insights in 7 days" is only a real promise if the product can tell you on
 * day 3 where you are and what is blocking you. Every milestone here is checked
 * against actual rows — history depth, stock coverage, data quality — not
 * against which wizard screens someone clicked through.
 *
 * Hides itself once everything is done, so it does not become permanent
 * furniture on the dashboard.
 */
export const ReadinessPanel = ({ compact = false }: { compact?: boolean }) => {
  const industry = useWorkspaceIndustry();
  const { data } = useQuery({
    queryKey: ["onboarding-readiness", industry],
    queryFn: readinessApi.get,
    staleTime: 60_000,
    retry: false,
  });

  if (!data) return null;
  if (data.percent_complete === 100) return null;

  return (
    <Card
      title="Your first week"
      description={
        data.day_of_journey
          ? `Day ${data.day_of_journey} · ${data.milestones_done} of ${data.milestones_total} milestones done`
          : `${data.milestones_done} of ${data.milestones_total} milestones done`
      }
      action={
        <Badge variant={data.on_track ? "success" : "warning"} dot>
          {data.on_track ? "On track" : `${data.blockers.length} blocking`}
        </Badge>
      }
    >
      <div className="mb-5 h-2 w-full overflow-hidden rounded-full bg-surface-3">
        <div
          className="h-full rounded-full bg-[var(--accent)] transition-all duration-500"
          style={{ width: `${data.percent_complete}%` }}
        />
      </div>

      {data.next_action && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/30 bg-[var(--accent-soft)] px-4 py-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-widest text-[var(--accent)]">
              Do this next
            </p>
            <p className="mt-0.5 text-sm font-semibold text-content">{data.next_action.label}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-content-muted">
              {data.next_action.detail}
            </p>
          </div>
          {data.next_action.action_route && (
            <Link to={data.next_action.action_route} className="shrink-0">
              <Button size="sm" icon={<ArrowRight size={14} />}>
                {data.next_action.action ?? "Go"}
              </Button>
            </Link>
          )}
        </div>
      )}

      {!compact && (
        <ol className="space-y-1">
          {data.milestones.map((m) => (
            <MilestoneRow key={m.key} milestone={m} />
          ))}
        </ol>
      )}
    </Card>
  );
};

function MilestoneRow({ milestone: m }: { milestone: ReadinessMilestone }) {
  const Icon = m.done ? Check : m.blocking ? Lock : CircleDashed;
  return (
    <li className="flex items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-surface-2">
      <span
        className={clsx(
          "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full",
          m.done
            ? "bg-emerald-500/15 text-emerald-600"
            : m.blocking
              ? "bg-rose-500/15 text-rose-600"
              : "bg-surface-3 text-content-subtle",
        )}
      >
        <Icon size={12} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={clsx(
              "text-sm font-medium",
              m.done ? "text-content-subtle line-through" : "text-content",
            )}
          >
            {m.label}
          </span>
          <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-content-subtle">
            <CalendarCheck size={10} /> Day {m.day}
          </span>
        </div>
        {!m.done && <p className="mt-0.5 text-xs leading-relaxed text-content-subtle">{m.detail}</p>}
      </div>
      {!m.done && m.action_route && (
        <Link
          to={m.action_route}
          className="shrink-0 text-xs font-semibold text-[var(--accent)] hover:underline"
        >
          Fix
        </Link>
      )}
    </li>
  );
}
