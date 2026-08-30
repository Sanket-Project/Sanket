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
import { useIndustryStore } from "@/stores/industry";
import { roiApi, type RoiLine } from "@/api/roi";

const WINDOWS = [30, 90, 180, 365];

/**
 * The ROI dashboard.
 *
 * The hard constraint here is honesty: a metric with no evidence shows as
 * "not measurable yet" with the reason, never as a zero or a guess. Every line
 * carries its `basis` and an expandable list of the actual decisions behind it,
 * because this is the screen a customer takes into a renewal conversation.
 */
export const ROIDashboardPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const [windowDays, setWindowDays] = useState(90);
  const [open, setOpen] = useState<string | null>(null);
  const { formatPrice } = useFormattedCurrency();

  const { data, isLoading } = useQuery({
    queryKey: ["roi-summary", industry, windowDays],
    queryFn: () => roiApi.summary(windowDays),
  });

  if (isLoading || !data) return <PageLoader />;

  const fmt = (n: number) => formatPrice(n, data.currency, { compact: true });
  const nothingYet = data.adoption.recommendations_accepted === 0;

  const renderValue = (line: RoiLine) => {
    if (line.value === null) return <span className="text-content-subtle">Not measurable yet</span>;
    if (line.unit === "currency") return fmt(line.value);
    if (line.unit === "percent") return `${line.value > 0 ? "+" : ""}${line.value}%`;
    return line.value.toLocaleString();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-emerald-600">
            <Award size={14} /> Return on investment
          </div>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">What SANKET saved you</h1>
          <p className="mt-1 text-content-subtle">
            Traced to the specific orders you accepted — not modelled, not projected.
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
            title="The ledger starts when you act on a recommendation"
            description={
              <>
                Each accepted order records what you ordered against what the old p90-cover policy
                would have ordered. The difference is the saving — auditable, per SKU, per day. There
                is nothing to show until then, and we will not estimate it.
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
        <>
          <Card className="bg-gradient-to-br from-emerald-500/10 to-transparent">
            <p className="text-xs font-bold uppercase tracking-widest text-content-subtle">
              Total value realised · last {data.window_days} days
            </p>
            <p className="mt-2 font-heading text-5xl font-bold tracking-tight text-emerald-600">
              {fmt(data.total_value_realized)}
            </p>
            <p className="mt-2 max-w-2xl text-sm text-content-muted">
              Sum of the rupee-denominated lines below across{" "}
              {data.adoption.recommendations_accepted} accepted recommendation
              {data.adoption.recommendations_accepted === 1 ? "" : "s"}. Percentages and counts are
              reported separately rather than folded into this figure.
            </p>
          </Card>

          <div className="space-y-3">
            {data.lines.map((line) => {
              const expanded = open === line.key;
              const hasDetails = line.details.length > 0;
              return (
                <Card key={line.key} padding="none">
                  <button
                    onClick={() => hasDetails && setOpen(expanded ? null : line.key)}
                    className="flex w-full items-start gap-4 p-5 text-left"
                    disabled={!hasDetails}
                  >
                    {hasDetails ? (
                      <span className="mt-1 shrink-0 text-content-subtle">
                        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </span>
                    ) : (
                      <span className="mt-1 shrink-0 text-content-subtle">
                        <Info size={16} />
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-heading text-[15px] font-semibold text-content">
                          {line.label}
                        </h3>
                        {line.evidence_count > 0 && (
                          <Badge variant="default">
                            {line.evidence_count} record{line.evidence_count === 1 ? "" : "s"}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1.5 text-xs leading-relaxed text-content-subtle">
                        {line.basis}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p
                        className={`font-heading text-2xl font-bold tabular-nums ${
                          line.value === null ? "" : "text-content"
                        }`}
                      >
                        {renderValue(line)}
                      </p>
                    </div>
                  </button>

                  {expanded && (
                    <div className="border-t border-line bg-surface-2/60 px-5 py-4">
                      <p className="mb-3 text-xs font-bold uppercase tracking-widest text-content-subtle">
                        Evidence
                      </p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-line text-left">
                              {Object.keys(line.details[0]).map((k) => (
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
                            {line.details.map((row, idx) => (
                              <tr key={idx} className="border-b border-line/60 last:border-0">
                                {Object.values(row).map((v, j) => (
                                  <td
                                    key={j}
                                    className="whitespace-nowrap px-3 py-2 font-mono text-xs tabular-nums text-content-muted"
                                  >
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
            })}
          </div>
        </>
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
