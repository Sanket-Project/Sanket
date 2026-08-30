import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Gauge } from "@/components/ui/icons";
import clsx from "clsx";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { forecastConfidenceApi, type ConfidenceBand, type SkuConfidence } from "@/api/forecasts";
import { useIndustryStore } from "@/stores/industry";

const BAND: Record<ConfidenceBand, { label: string; variant: "success" | "info" | "warning" | "danger" }> = {
  high: { label: "High", variant: "success" },
  moderate: { label: "Moderate", variant: "info" },
  low: { label: "Low", variant: "warning" },
  insufficient: { label: "Insufficient data", variant: "danger" },
};

function tone(score: number) {
  if (score >= 80) return "text-emerald-600";
  if (score >= 60) return "text-cyan-600";
  if (score >= 40) return "text-amber-600";
  return "text-rose-600";
}

/**
 * Forecast confidence.
 *
 * A p10/p50/p90 band shows uncertainty; it does not show *why*. This ranks the
 * portfolio worst-first and names the cause — "only 9 weeks of history", "62%
 * of weeks had no sales" — because a low score is an instruction to go fix the
 * data, not a number to hide.
 */
export const ForecastConfidencePanel = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const [open, setOpen] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["forecast-confidence", industry],
    queryFn: () => forecastConfidenceApi.list(50),
    retry: false,
  });

  if (isLoading) return null;

  if (!data || data.scored === 0) {
    return (
      <Card padding="none">
        <EmptyState
          variant="subtle"
          icon={<Gauge size={20} />}
          title="No confidence scores yet"
          description={data?.reason ?? "Run a forecast to score how much it can be trusted."}
        />
      </Card>
    );
  }

  return (
    <Card
      title="How much can you trust this forecast?"
      description={`${data.scored} SKUs scored — least trustworthy first, so you know what to fix.`}
      action={
        <div className="text-right">
          <p className={clsx("font-heading text-2xl font-bold tabular-nums", tone(data.portfolio_confidence ?? 0))}>
            {data.portfolio_confidence}%
          </p>
          <p className="text-[10px] font-bold uppercase tracking-widest text-content-subtle">
            Portfolio
          </p>
        </div>
      }
    >
      {data.by_band && (
        <div className="mb-4 flex flex-wrap gap-2">
          {(Object.keys(BAND) as ConfidenceBand[])
            .filter((b) => (data.by_band?.[b] ?? 0) > 0)
            .map((b) => (
              <Badge key={b} variant={BAND[b].variant}>
                {data.by_band?.[b]} {BAND[b].label.toLowerCase()}
              </Badge>
            ))}
        </div>
      )}

      <ul className="divide-y divide-line">
        {data.skus.map((s) => (
          <Row key={s.sku_id} sku={s} open={open === s.sku_id} onToggle={() => setOpen(open === s.sku_id ? null : s.sku_id)} />
        ))}
      </ul>
    </Card>
  );
};

function Row({ sku, open, onToggle }: { sku: SkuConfidence; open: boolean; onToggle: () => void }) {
  return (
    <li>
      <button onClick={onToggle} className="flex w-full items-center gap-3 py-2.5 text-left">
        <span className="shrink-0 text-content-subtle">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="w-32 shrink-0 truncate font-mono text-xs font-semibold text-content">
          {sku.sku_code ?? sku.sku_id.slice(0, 8)}
        </span>
        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
          <span
            className={clsx(
              "block h-full rounded-full",
              sku.confidence >= 80
                ? "bg-emerald-500"
                : sku.confidence >= 60
                  ? "bg-cyan-500"
                  : sku.confidence >= 40
                    ? "bg-amber-500"
                    : "bg-rose-500",
            )}
            style={{ width: `${Math.max(2, sku.confidence)}%` }}
          />
        </span>
        <span className={clsx("w-12 shrink-0 text-right text-sm font-bold tabular-nums", tone(sku.confidence))}>
          {sku.confidence}%
        </span>
        <Badge variant={BAND[sku.band].variant} className="hidden shrink-0 sm:inline-flex">
          {BAND[sku.band].label}
        </Badge>
      </button>

      {open && (
        <ul className="mb-3 ml-8 space-y-1">
          {sku.reasons.map((r, i) => (
            <li key={i} className="flex gap-2 text-xs leading-relaxed text-content-muted">
              <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-content-subtle" />
              {r}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
