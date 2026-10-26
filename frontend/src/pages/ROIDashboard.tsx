import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Award, ChevronDown, ChevronRight, Info, Target } from "@/components/ui/icons";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageLoader } from "@/components/ui/Spinner";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { roiApi, type RoiLine, type RoiTier } from "@/api/roi";

const WINDOWS = [30, 90, 180, 365];
const TIER_ORDER: RoiTier[] = ["opportunity", "estimated_at_approval", "observed"];
const STATUS_LABEL: Record<string, string> = {
  estimate: "Estimate",
  measured: "Measured",
  not_measurable: "Not measurable yet",
};

/**
 * The ROI dashboard.
 *
 * Every figure is one of three kinds and is shown under its own heading:
 * opportunity on open recommendations, estimates frozen when a recommendation
 * was approved, and observed outcomes. Approving is a decision, not an
 * outcome, so nothing here is presented as money saved until receipts and
 * sales could prove it — and there is no grand total of unlike measures.
 */
export const ROIDashboardPage = () => {
  const industry = useWorkspaceIndustry();
  const [windowDays, setWindowDays] = useState(90);
  const [open, setOpen] = useState<string | null>(null);
  const { formatPrice } = useFormattedCurrency();

  const { data, isLoading } = useQuery({
    queryKey: ["roi-summary", industry, windowDays],
    queryFn: () => roiApi.summary(windowDays),
  });

  if (isLoading || !data) return <PageLoader />;

  const nothingYet =
    data.adoption.recommendations_accepted === 0 && data.adoption.recommendations_open === 0;

  const renderValue = (line: RoiLine) => {
    if (line.unit === "currency") {
      const entries = Object.entries(line.values_by_currency ?? {});
      if (line.value === null && entries.length) {
        return entries.map(([code, v]) => formatPrice(v, code, { compact: true })).join(" · ");
      }
      if (line.value === null) return <span className="text-content-subtle">Not measurable yet</span>;
      return formatPrice(line.value, line.currency ?? data.currency, { compact: true });
    }
    if (line.value === null) return <span className="text-content-subtle">Not measurable yet</span>;
    if (line.unit === "percent") return `${line.value > 0 ? "+" : ""}${line.value}%`;
    return line.value.toLocaleString();
  };

  const renderLine = (line: RoiLine) => {
    const expanded = open === line.key;
    const hasDetails = line.details.length > 0;
    return (
      <Card key={line.key} padding="none">
        <button
          onClick={() => hasDetails && setOpen(expanded ? null : line.key)}
          className="flex w-full items-start gap-4 p-5 text-left"
          disabled={!hasDetails}
        >
          <span className="mt-1 shrink-0 text-content-subtle">
            {hasDetails ? (expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />) : <Info size={16} />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-heading text-[15px] font-semibold text-content">{line.label}</h3>
              {line.evidence_count > 0 && (
                <Badge variant="default">
                  {line.evidence_count} record{line.evidence_count === 1 ? "" : "s"}
                </Badge>
              )}
              {!line.additive && <Badge variant="warning">Derived — not additional</Badge>}
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-content-subtle">{line.basis}</p>
          </div>
          <div className="shrink-0 text-right">
            <p className="font-heading text-2xl font-bold tabular-nums text-content">{renderValue(line)}</p>
          </div>
        </button>

        {expanded && (
          <div className="border-t border-line bg-surface-2/60 px-5 py-4">
            <p className="mb-3 text-xs font-bold uppercase tracking-widest text-content-subtle">Evidence</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left">
                    {Object.keys(line.details[0]).map((k) => (
                      <th key={k} className="whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">
                        {k.replace(/_/g, " ")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {line.details.map((row, idx) => (
                    <tr key={idx} className="border-b border-line/60 last:border-0">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="whitespace-nowrap px-3 py-2 font-mono text-xs tabular-nums text-content-muted">
                          {v === null || v === undefined ? "—" : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-emerald-600">
            <Award size={14} /> Return on investment
          </div>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Value from your decisions</h1>
          <p className="mt-1 text-content-subtle">
            Estimates are labelled as estimates. Nothing here is money saved until supplier orders,
            receipts and sales confirm it.
          </p>
        </div>
        <div className="flex gap-1.5">
          {WINDOWS.map((w) => (
            <button
              key={w}
              onClick={() => setWindowDays(w)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                windowDays === w
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-line text-content-muted hover:text-content"
              }`}
            >
              {w}d
            </button>
          ))}
        </div>
      </div>

      {nothingYet ? (
        <Card padding="none">
          <EmptyState
            icon={<Award size={22} />}
            title="The ledger starts when there are recommendations to act on"
            description={
              <>
                Each approved order records what you ordered against what the old P90-cover policy
                would have ordered. That difference is an estimate made at approval — it becomes a
                saving only once the order is received and sold through.
              </>
            }
            action={
              <Link to="/workspace/decisions">
                <Button icon={<Target size={15} />}>Review the decision queue</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        TIER_ORDER.map((key) => {
          const tier = data.tiers[key];
          if (!tier) return null;
          return (
            <section key={key} className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-heading text-lg font-semibold text-content">{tier.label}</h2>
                <Badge variant={tier.status === "measured" ? "success" : "default"}>
                  {STATUS_LABEL[tier.status] ?? tier.status}
                </Badge>
              </div>
              {tier.lines.map(renderLine)}
            </section>
          );
        })
      )}

      <Card className="border-dashed">
        <div className="flex gap-3">
          <Info size={16} className="mt-0.5 shrink-0 text-content-subtle" />
          <p className="text-sm leading-relaxed text-content-muted">{data.caveat}</p>
        </div>
      </Card>
    </div>
  );
};
