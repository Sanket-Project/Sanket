import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  LineChart,
  Package,
  RefreshCw,
  ShieldCheck,
  Target,
  X,
} from "@/components/ui/icons";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageLoader } from "@/components/ui/Spinner";
import { KPICard } from "@/components/charts/KPICard";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getErrorMessage } from "@/utils/errors";
import {
  decisionsApi,
  type Decision,
  type DecisionUrgency,
  type ConfidenceBand,
  type SkippedSku,
} from "@/api/decisions";
import { invalidatePlanningData } from "@/api/planningKeys";

const URGENCY_STYLE: Record<DecisionUrgency, { label: string; variant: "danger" | "warning" | "info" | "default" }> = {
  critical: { label: "Order now", variant: "danger" },
  high: { label: "This week", variant: "warning" },
  normal: { label: "This cycle", variant: "info" },
  low: { label: "No rush", variant: "default" },
};

const CONFIDENCE_STYLE: Record<ConfidenceBand, { variant: "success" | "info" | "warning" | "danger" }> = {
  high: { variant: "success" },
  moderate: { variant: "info" },
  low: { variant: "warning" },
  insufficient: { variant: "danger" },
};

/**
 * The decision queue.
 *
 * A forecast is a number; this page is the sentence built from it — what to
 * order, why, and what it is worth. Every row can be expanded to the full
 * derivation, because a planner will not commit capital to a number they cannot
 * interrogate.
 */
export const DecisionsPage = () => {
  const industry = useWorkspaceIndustry();
  const queryClient = useQueryClient();
  const { formatPrice } = useFormattedCurrency();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"open" | "accepted" | "dismissed">("open");
  const [sortBy, setSortBy] = useState<"urgency" | "cover" | "value">("urgency");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [skipped, setSkipped] = useState<SkippedSku[]>([]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["decisions", industry, statusFilter],
    queryFn: () => decisionsApi.list({ status: statusFilter, limit: 200 }),
  });

  // Accepting or recomputing changes the queue, ROI and every screen that
  // shows open decisions (sidebar badges, dashboard, inventory next actions).
  const invalidate = () => {
    void invalidatePlanningData(queryClient);
  };

  const refresh = useMutation({
    mutationFn: decisionsApi.refresh,
    onSuccess: (res) => {
      invalidate();
      setSkipped(res.skipped ?? []);
      if (res.reason) toast(res.reason, { icon: "ℹ️", duration: 6000 });
      else toast.success(`${res.generated} recommendation(s) from ${res.skus_evaluated} SKUs`);
    },
    onError: (e) => toast.error(getErrorMessage(e)),
  });

  // Refresh whether or not the server accepted: a 409 (e.g. expired) means the
  // queue on screen is out of date.
  const accept = useMutation({
    mutationFn: ({ id, units }: { id: string; units?: number }) => decisionsApi.accept(id, { units }),
    onSuccess: () => toast.success("Recorded — this now counts towards your ROI ledger"),
    onError: (e) => toast.error(getErrorMessage(e)),
    onSettled: invalidate,
  });

  const dismiss = useMutation({
    mutationFn: (id: string) => decisionsApi.dismiss(id),
    onSuccess: () => toast.success("Dismissed"),
    onError: (e) => toast.error(getErrorMessage(e)),
    onSettled: invalidate,
  });

  // Each accept is independent: one expired row must not hide that the
  // others were recorded.
  const bulkAccept = useMutation({
    mutationFn: (items: Decision[]) =>
      Promise.allSettled(items.map((decision) => decisionsApi.accept(decision.id, {
        units: decision.kind === "purchase_order" ? decision.recommended_units : undefined,
      }))),
    onSuccess: (outcomes) => {
      setSelected(new Set());
      const failed = outcomes.filter((o): o is PromiseRejectedResult => o.status === "rejected");
      const recorded = outcomes.length - failed.length;
      if (failed.length) {
        toast.error(
          `${recorded} recorded, ${failed.length} could not be accepted: ${getErrorMessage(failed[0].reason)}`,
        );
      } else {
        toast.success(`${recorded} decisions recorded in your ROI ledger`);
      }
    },
    onError: (e) => toast.error(getErrorMessage(e)),
    onSettled: invalidate,
  });

  const decisions = useMemo(() => data?.decisions ?? [], [data?.decisions]);
  const visibleDecisions = useMemo(() => {
    const urgencyRank: Record<DecisionUrgency, number> = { critical: 0, high: 1, normal: 2, low: 3 };
    return [...decisions].sort((a, b) => {
      if (sortBy === "cover") return (a.inputs.days_of_cover ?? Number.POSITIVE_INFINITY) - (b.inputs.days_of_cover ?? Number.POSITIVE_INFINITY);
      // Unknown value sorts last rather than as zero.
      if (sortBy === "value") return (b.economics.revenue_protected ?? -1) - (a.economics.revenue_protected ?? -1);
      return urgencyRank[a.urgency] - urgencyRank[b.urgency];
    });
  }, [decisions, sortBy]);
  const totals = data?.totals;
  const currency = totals?.currency ?? "INR";
  const fmt = (n: number | null | undefined) =>
    n == null ? "Unavailable" : formatPrice(n, currency, { compact: true });
  const missingCost = decisions.filter((d) => d.kind === "purchase_order" && d.unit_cost == null).length;
  const missingPrice = decisions.filter((d) => d.kind === "purchase_order" && d.unit_price == null).length;
  const valuationNote = [
    missingCost ? `${missingCost} of ${totals?.purchase_orders ?? decisions.length} orders missing unit cost` : null,
    missingPrice ? `${missingPrice} missing unit price` : null,
  ].filter(Boolean).join(" · ");

  if (isLoading) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-[var(--accent)]">
            <Target size={14} /> Decision engine
          </div>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">What to order, and why</h1>
          <p className="mt-1 text-content-subtle">
            Forecasts turned into purchase decisions, sized against your lead times, service level
            and stock on hand.
          </p>
        </div>
        <Button
          onClick={() => refresh.mutate()}
          loading={refresh.isPending}
          icon={<RefreshCw size={15} />}
        >
          Recompute from latest forecast
        </Button>
      </div>

      {isError && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
          <span className="flex items-center gap-2"><AlertTriangle size={16} /> Decisions could not be loaded. This is not an empty queue.</span>
          <Button size="sm" variant="secondary" onClick={() => void refetch()}>Retry</Button>
        </div>
      )}

      {skipped.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <p className="font-semibold">{skipped.length} SKU{skipped.length === 1 ? " was" : "s were"} left out of the last recompute</p>
          <ul className="mt-1 space-y-0.5 text-xs">
            {skipped.slice(0, 8).map((item) => (
              <li key={item.sku_code}><span className="font-mono font-semibold">{item.sku_code}</span> — {item.reason}</li>
            ))}
          </ul>
          {skipped.length > 8 && <p className="mt-1 text-xs">…and {skipped.length - 8} more.</p>}
          <Link to="/workspace/inventory" className="mt-1 inline-block text-xs font-semibold underline">Update stock in Inventory</Link>
        </div>
      )}

      {totals && totals.purchase_orders > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KPICard
            label="Orders to place"
            value={totals.purchase_orders}
            subtitle={`${totals.units_to_order.toLocaleString()} units`}
            icon={<Package size={16} />}
            tone={totals.critical > 0 ? "danger" : "default"}
          />
          <KPICard
            label="Capital committed"
            value={fmt(totals.capital_committed)}
            subtitle={totals.capital_committed == null ? `Needs unit cost — ${valuationNote}` : "If you accept every order"}
            tone="default"
          />
          <KPICard
            label="Working capital vs. old policy (estimate)"
            value={fmt(totals.working_capital_released_vs_baseline)}
            subtitle={totals.working_capital_released_vs_baseline == null ? "Needs unit cost for every order" : "If every order is placed as recommended, versus covering P90 the old way"}
            tone="success"
          />
          <KPICard
            label="Revenue at risk covered (estimate)"
            value={fmt(totals.revenue_protected)}
            subtitle={totals.revenue_protected == null ? "Needs unit price for every order" : "Demand your stock cannot cover today"}
            tone={(totals.revenue_protected ?? 0) > 0 ? "warning" : "default"}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2.5">
        <div className="flex gap-2">
          {(["open", "accepted", "dismissed"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold capitalize transition-colors ${
              statusFilter === s
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-line text-content-muted hover:text-content"
            }`}
          >
            {s}
          </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {statusFilter === "open" && selected.size > 0 && (
            <Button
              size="sm"
              icon={<Check size={14} />}
              loading={bulkAccept.isPending}
              onClick={() => bulkAccept.mutate(visibleDecisions.filter((decision) => selected.has(decision.id)))}
            >
              Accept selected ({selected.size})
            </Button>
          )}
          <label className="flex items-center gap-2 text-xs font-medium text-content-muted">
            Sort
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value as typeof sortBy)}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-content"
              aria-label="Sort decisions"
            >
              <option value="urgency">Urgency</option>
              <option value="cover">Cover left</option>
              <option value="value">Revenue protected</option>
            </select>
          </label>
        </div>
      </div>

      {isError ? null : decisions.length === 0 ? (
        <Card padding="none">
          <EmptyState
            icon={<Target size={22} />}
            title={
              statusFilter === "open"
                ? "No open recommendations"
                : `Nothing ${statusFilter} yet`
            }
            description={
              statusFilter === "open" ? (
                <>
                  Recommendations are derived from your latest completed forecast run — they are
                  never estimated. Run a forecast, then recompute here.
                </>
              ) : (
                "Decisions you act on will appear here, and feed the ROI dashboard."
              )
            }
            action={
              statusFilter === "open" ? (
                <div className="flex gap-2">
                  <Link to="/workspace/forecasts">
                    <Button variant="secondary" icon={<LineChart size={15} />}>
                      Go to forecasts
                    </Button>
                  </Link>
                  <Button onClick={() => refresh.mutate()} loading={refresh.isPending}>
                    Recompute
                  </Button>
                </div>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {visibleDecisions.map((d) => (
            <DecisionRow
              key={d.id}
              decision={d}
              expanded={expanded === d.id}
              onToggle={() => setExpanded(expanded === d.id ? null : d.id)}
              onAccept={(units) => accept.mutate({ id: d.id, units })}
              onDismiss={() => dismiss.mutate(d.id)}
              busy={accept.isPending || dismiss.isPending}
              selected={selected.has(d.id)}
              onSelectedChange={(checked) => setSelected((current) => {
                const next = new Set(current);
                if (checked) next.add(d.id);
                else next.delete(d.id);
                return next;
              })}
            />
          ))}
        </div>
      )}
    </div>
  );
};

function DecisionRow({
  decision: d,
  expanded,
  onToggle,
  onAccept,
  onDismiss,
  busy,
  selected,
  onSelectedChange,
}: {
  decision: Decision;
  expanded: boolean;
  onToggle: () => void;
  onAccept: (units?: number) => void;
  onDismiss: () => void;
  busy: boolean;
  selected: boolean;
  onSelectedChange: (checked: boolean) => void;
}) {
  const { formatPrice } = useFormattedCurrency();
  const [units, setUnits] = useState<number>(d.recommended_units);
  const fmt = (n: number) => formatPrice(n, d.currency, { compact: true });
  const urgency = URGENCY_STYLE[d.urgency];
  const confidence = CONFIDENCE_STYLE[d.confidence_band];
  const isOpen = d.status === "open";
  const cover = d.inputs?.days_of_cover;

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-start">
        {isOpen && (
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelectedChange(event.target.checked)}
            aria-label={`Select ${d.sku_code ?? "decision"}`}
            className="mt-1 h-4 w-4 shrink-0 rounded border-line accent-[var(--accent)]"
          />
        )}
        <button
          onClick={onToggle}
          className="mt-0.5 hidden shrink-0 text-content-subtle transition-colors hover:text-content lg:block"
          aria-label={expanded ? "Hide working" : "Show working"}
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-bold text-content">{d.sku_code ?? d.sku_id.slice(0, 8)}</span>
            <Badge variant={urgency.variant} dot>
              {urgency.label}
            </Badge>
            <Badge variant={confidence.variant}>{d.confidence}% confidence</Badge>
            {d.linked_alert_id && (
              <Badge variant="danger">
                <AlertTriangle size={11} /> Needs attention
              </Badge>
            )}
            {d.status !== "open" && <Badge variant="default">{d.status}</Badge>}
            {d.inputs?.lead_time_assumed && (
              <Badge variant="warning">Lead time assumed ({d.inputs.lead_time_days}-day default)</Badge>
            )}
          </div>

          <h3 className="mt-2 text-lg font-semibold tracking-tight text-content">{d.headline}</h3>

          {/* The two or three clauses that justify the number, inline. */}
          <ul className="mt-2 space-y-1">
            {d.reasons.slice(0, expanded ? d.reasons.length : 3).map((r) => (
              <li key={r.code} className="flex gap-2 text-sm text-content-muted">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-content-subtle" />
                <span>{r.text}</span>
              </li>
            ))}
          </ul>

          {!expanded && d.reasons.length > 3 && (
            <button
              onClick={onToggle}
              className="mt-2 text-xs font-semibold text-[var(--accent)] hover:underline"
            >
              Show the full working ({d.reasons.length - 3} more)
            </button>
          )}
        </div>

        <div className="flex shrink-0 flex-col gap-3 lg:w-72 xl:w-80">
          <dl className="space-y-1.5 rounded-xl bg-surface-2 p-3 text-sm">
            {typeof cover === "number" && (
              <div className="flex justify-between">
                <dt className="text-content-subtle">Cover left</dt>
                <dd className={cover <= d.inputs.lead_time_days ? "font-semibold text-rose-600" : "font-semibold"}>
                  {cover.toFixed(0)} days
                </dd>
              </div>
            )}
            {d.economics.revenue_protected != null && d.economics.revenue_protected > 0 && (
              <div className="flex justify-between">
                <dt className="text-content-subtle">Revenue protected</dt>
                <dd className="font-semibold text-emerald-600">{fmt(d.economics.revenue_protected)}</dd>
              </div>
            )}
            {d.economics.working_capital_released != null && d.economics.working_capital_released > 0 && (
              <div className="flex justify-between">
                <dt className="text-content-subtle">vs. old policy</dt>
                <dd className="font-semibold text-emerald-600">
                  −{fmt(d.economics.working_capital_released)}
                </dd>
              </div>
            )}
            {d.economics.capital_locked != null && (
              <div className="flex justify-between">
                <dt className="text-content-subtle">Capital locked up</dt>
                <dd className="font-semibold text-amber-600">{fmt(d.economics.capital_locked)}</dd>
              </div>
            )}
            {d.unit_cost == null && (
              <div className="flex justify-between">
                <dt className="text-content-subtle">Capital needed</dt>
                <dd className="font-semibold text-content-subtle" title="No unit cost recorded for this SKU">Unavailable</dd>
              </div>
            )}
          </dl>

          {isOpen && d.kind === "purchase_order" && (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                value={units}
                onChange={(e) => setUnits(Number(e.target.value))}
                className="w-20 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm font-semibold tabular-nums"
                aria-label="Units to order"
              />
              <Button size="sm" icon={<Check size={14} />} disabled={busy} onClick={() => onAccept(units)}>
                Accept
              </Button>
              <Button
                size="sm"
                variant="ghost"
                icon={<X size={14} />}
                disabled={busy}
                onClick={onDismiss}
                aria-label="Dismiss recommendation"
                title="Dismiss recommendation"
              >
                Dismiss
              </Button>
            </div>
          )}
          {isOpen && d.kind !== "purchase_order" && (
            <div className="flex gap-2">
              <Button size="sm" icon={<Check size={14} />} disabled={busy} onClick={() => onAccept()}>
                Acknowledge
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={onDismiss}>
                Dismiss
              </Button>
            </div>
          )}
          {!isOpen && d.accepted_units != null && (
            <p className="text-xs text-content-subtle">
              Committed {d.accepted_units.toLocaleString()} units
            </p>
          )}
        </div>
      </div>

      {expanded && <Working decision={d} />}
    </Card>
  );
}

/** The full derivation. Nothing here is rounded away — it is the audit trail. */
function Working({ decision: d }: { decision: Decision }) {
  const i = d.inputs;
  const rows: Array<[string, string]> = [
    ["Supplier lead time", `${i.lead_time_days} days`],
    ["Review cycle", `${i.review_period_days} days`],
    ["Protection window", `${i.protection_days} days`],
    ["Forecast demand (p50) over window", `${i.demand_p50_over_window?.toLocaleString()} units`],
    ["Pessimistic demand (p90) over window", `${i.demand_p90_over_window?.toLocaleString()} units`],
    ["Demand σ over window", `${i.sigma_over_window?.toLocaleString()} units`],
    ["Service level", `${(i.service_level * 100).toFixed(0)}% (z = ${i.z})`],
    ["Safety stock", `${Math.round(i.safety_stock_units).toLocaleString()} units`],
    ["Order-up-to level", `${Math.round(i.order_up_to).toLocaleString()} units`],
    ["On hand", `${Math.round(i.on_hand_units).toLocaleString()} units`],
    ["Reserved", `${Math.round(i.reserved_units).toLocaleString()} units`],
    ["Inbound", `${Math.round(i.inbound_units).toLocaleString()} units`],
    ["Stock position", `${Math.round(i.position_units).toLocaleString()} units`],
    ["Supplier MOQ", i.moq.toLocaleString()],
  ];

  return (
    <div className="border-t border-line bg-surface-2/60 px-5 py-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-content-subtle">
        <ShieldCheck size={13} /> How this number was reached
      </div>
      <dl className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 text-sm">
            <dt className="text-content-subtle">{k}</dt>
            <dd className="shrink-0 font-medium tabular-nums text-content">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 rounded-lg bg-surface p-3 text-xs leading-relaxed text-content-subtle">
        <span className="font-semibold text-content">Baseline comparison.</span> A spreadsheet policy
        covering p90 demand across the whole window would order{" "}
        <strong>{d.baseline_units.toLocaleString()}</strong> units. Pooling variance across the{" "}
        {i.protection_days} days instead lets you hit the same {(i.service_level * 100).toFixed(0)}%
        service level with <strong>{d.recommended_units.toLocaleString()}</strong>.
      </p>
    </div>
  );
}
