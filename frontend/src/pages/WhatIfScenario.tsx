import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  FlaskConical,
  Play,
  RotateCcw,
  TrendingDown,
  TrendingUp,
} from "@/components/ui/icons";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ScenarioAssistant } from "@/components/ai/ScenarioAssistant";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { getErrorMessage } from "@/utils/errors";
import {
  DEFAULT_LEVERS,
  scenariosApi,
  type ScenarioLevers,
  type ScenarioReadiness,
  type SimulationResult,
} from "@/api/scenarios";

type MoneyFmt = (n: number | null | undefined) => string;
const UNAVAILABLE = "Unavailable";

const RECOMMENDED_SCENARIO: ScenarioLevers = {
  ...DEFAULT_LEVERS,
  name: "Supplier outage (8 weeks)",
  preset: "supplier_failure",
  supplier_outage_weeks: 8,
};

const PHYSICAL_LEVERS: Array<keyof ScenarioLevers> = [
  "demand_shock_pct",
  "price_change_pct",
  "price_elasticity",
  "lead_time_delta_days",
  "cost_change_pct",
  "supplier_outage_weeks",
  "supplier_outage_sku_ids",
  "service_level",
  "ramp_weeks",
  "horizon_weeks",
  "review_weeks",
  "sku_ids",
];

const samePhysicalLevers = (a: ScenarioLevers, b: ScenarioLevers) =>
  PHYSICAL_LEVERS.every((key) => JSON.stringify(a[key] ?? null) === JSON.stringify(b[key] ?? null));

/**
 * The digital twin.
 *
 * Levers move physical parameters — demand, supplier lead time, unit cost,
 * supplier availability — and the backend runs the weekly inventory recursion
 * twice (baseline and scenario) over the tenant's real SKUs, real stock and
 * real forecast. Nothing on this page is scaled or synthesised; if there is no
 * forecast to simulate against, it says so instead of drawing a curve.
 */
export const WhatIfScenarioPage = () => {
  const { formatPrice } = useFormattedCurrency();
  const [levers, setLevers] = useState<ScenarioLevers>(() => ({ ...RECOMMENDED_SCENARIO }));
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [lastSuccessfulLevers, setLastSuccessfulLevers] = useState<ScenarioLevers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explainAI, setExplainAI] = useState(false);
  const hasStartedRecommendedRun = useRef(false);

  const { data: presets } = useQuery({
    queryKey: ["scenario-presets"],
    queryFn: scenariosApi.presets,
    staleTime: 60 * 60_000,
  });

  const run = useMutation({
    mutationFn: scenariosApi.simulate,
    onSuccess: (res, submittedLevers) => {
      setResult(res);
      // The server never simulates past the forecast; keep the slider honest.
      const available = res.config.forecast_weeks_available;
      const clamp = (l: ScenarioLevers) =>
        available && l.horizon_weeks > available ? { ...l, horizon_weeks: available } : l;
      setLastSuccessfulLevers(clamp(submittedLevers));
      setLevers((current) => clamp(current));
      setError(null);
    },
    onError: (e) => {
      setError(getErrorMessage(e));
    },
  });
  const runScenario = run.mutate;

  useEffect(() => {
    // Dispatch after the committed effect mount. StrictMode's initial cleanup
    // otherwise detaches the mutation observer while its request is in flight,
    // leaving the observer pending even though onSuccess receives the result.
    const initialRun = window.setTimeout(() => {
      if (hasStartedRecommendedRun.current) return;
      hasStartedRecommendedRun.current = true;
      runScenario(RECOMMENDED_SCENARIO);
    }, 0);
    return () => window.clearTimeout(initialRun);
  }, [runScenario]);

  const set = <K extends keyof ScenarioLevers>(key: K, value: ScenarioLevers[K]) => {
    setLevers((l) => ({ ...l, [key]: value, preset: null }));
    setError(null);
  };

  const applyPreset = (key: string, scenario: Partial<ScenarioLevers>, label: string) => {
    const next = { ...DEFAULT_LEVERS, ...scenario, name: label, preset: key };
    setLevers(next);
    setError(null);
    run.mutate(next);
  };

  const reset = () => {
    setLevers({ ...DEFAULT_LEVERS });
    setError(null);
  };

  const currency = result?.result.currency ?? "INR";
  const fmt: MoneyFmt = (n) => (n == null ? UNAVAILABLE : formatPrice(n, currency, { compact: true }));
  const maxHorizon = result?.config.forecast_weeks_available ?? 52;
  const hasUnrunChanges = Boolean(
    result && lastSuccessfulLevers && !samePhysicalLevers(levers, lastSuccessfulLevers),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-[var(--accent)]">
            <FlaskConical size={14} /> Digital twin
          </div>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Scenario simulator</h1>
          <p className="mt-1 max-w-2xl text-content-subtle">
            Move a lever and we replay your actual supply chain week by week — arrivals, demand,
            shortfalls, reorders — against the same run with nothing changed.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" icon={<RotateCcw size={15} />} onClick={reset}>
            Reset
          </Button>
          <Button icon={<Play size={15} />} loading={run.isPending} onClick={() => run.mutate({ ...levers, explain_ai: explainAI })}>
            Run simulation
          </Button>
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-content-subtle"><input type="checkbox" checked={explainAI} onChange={(e) => setExplainAI(e.target.checked)} />Include an AI explanation of engine results</label>
      {result?.ai_explanation && <aside className="space-y-2 rounded-xl border border-line bg-surface p-4 text-sm" aria-label="Scenario explanation">
        {result.ai_explanation.state === "success" ? <><p className="text-xs text-content-subtle">AI-generated · based on simulation engine results</p>{result.ai_explanation.blocks.map((block, i) => <p key={i}>{block.text} <a href="/workspace/scenarios" className="text-accent underline">Source: simulation</a></p>)}</> : <p role="status">AI explanation unavailable. The engine results remain available below.</p>}
      </aside>}

      <ScenarioAssistant onApply={(assumptions) => {
        setLevers((current) => ({ ...DEFAULT_LEVERS, horizon_weeks: current.horizon_weeks,
          review_weeks: current.review_weeks, ...assumptions, preset: null, name: "Reviewed assumptions" }));
        setError(null);
      }} />

      {/* Presets — the questions people actually ask */}
      {presets && (
        <div className="flex flex-wrap gap-2">
          {presets.presets.map((p) => (
            <button
              key={p.key}
              title={p.description}
              onClick={() => applyPreset(p.key, p.scenario, p.label)}
              className={`rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors ${
                levers.preset === p.key
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-line text-content-muted hover:border-line-strong hover:text-content"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        {/* min-w-0 lets grid children shrink below their content on phones. */}
        <div data-layout="levers" className="min-w-0">
        <Card title="Levers" description="Each one changes the world, not the chart.">
          <div className="space-y-5">
            <Slider
              label="Demand"
              value={levers.demand_shock_pct}
              min={-90}
              max={200}
              step={5}
              unit="%"
              onChange={(v) => set("demand_shock_pct", v)}
            />
            <Slider
              label="Ramp the demand change in over"
              value={levers.ramp_weeks}
              min={0}
              max={26}
              step={1}
              unit=" wk"
              onChange={(v) => set("ramp_weeks", v)}
            />
            <Slider
              label="Selling price"
              value={levers.price_change_pct}
              min={-50}
              max={50}
              step={1}
              unit="%"
              onChange={(v) => set("price_change_pct", v)}
              hint={`Volume responds at ${levers.price_elasticity} elasticity`}
            />
            <Slider
              label="Supplier lead time"
              value={levers.lead_time_delta_days}
              min={-30}
              max={120}
              step={1}
              unit=" days"
              onChange={(v) => set("lead_time_delta_days", v)}
            />
            <Slider
              label="Unit cost (tariffs, FX)"
              value={levers.cost_change_pct}
              min={-50}
              max={100}
              step={1}
              unit="%"
              onChange={(v) => set("cost_change_pct", v)}
            />
            <Slider
              label="Supplier outage"
              value={levers.supplier_outage_weeks}
              min={0}
              max={26}
              step={1}
              unit=" wk"
              onChange={(v) => set("supplier_outage_weeks", v)}
              hint="Nothing arrives; in-transit stock is delayed, not lost"
            />
            <Slider
              label="Horizon"
              value={Math.min(levers.horizon_weeks, maxHorizon)}
              min={Math.min(4, maxHorizon)}
              max={maxHorizon}
              step={1}
              unit=" wk"
              onChange={(v) => set("horizon_weeks", v)}
              hint={result?.config.forecast_weeks_available ? `Limited to the ${maxHorizon} weeks the forecast covers` : undefined}
            />
          </div>
        </Card>
        </div>

        <div className="min-w-0 space-y-4">
          {error && !result && (
            <Card padding="none">
              <EmptyState
                icon={<AlertTriangle size={22} />}
                title="Nothing to simulate against"
                description={error}
                action={
                  <Link to="/workspace/forecasts">
                    <Button variant="secondary">Generate a forecast</Button>
                  </Link>
                }
              />
            </Card>
          )}

          {!result && !error && (
            <Card className="overflow-hidden">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-widest text-[var(--accent)]">
                    Recommended starter scenario
                  </p>
                  <h2 className="mt-1 font-heading text-lg font-semibold text-content">
                    Baseline vs supplier outage
                  </h2>
                </div>
                <Badge variant="primary" dot>
                  {run.isPending ? "Running" : "Ready"}
                </Badge>
              </div>
              <p className="mt-3 max-w-xl text-sm leading-relaxed text-content-muted">
                We automatically compare normal operations with an eight-week supplier outage so
                the simulator opens with an actionable point of reference.
              </p>
              <div
                className="mt-5 rounded-2xl border border-line bg-surface-2 px-4 py-5"
                role="status"
                aria-live="polite"
              >
                <div className="flex items-center gap-3">
                  <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--accent)]" />
                  <p className="text-sm font-medium text-content">
                    {run.isPending
                      ? "Replaying inventory, demand and replenishment week by week…"
                      : "Preparing the recommended comparison…"}
                  </p>
                </div>
                <div className="mt-5 space-y-3" aria-hidden="true">
                  <div className="h-px w-full bg-line" />
                  <div className="h-px w-4/5 bg-line-strong" />
                  <div className="h-px w-3/5 bg-[var(--accent)] opacity-35" />
                </div>
              </div>
            </Card>
          )}

          {error && result && (
            <div
              className="flex items-start gap-2.5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
              role="alert"
            >
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <p>
                {error} The last successful comparison is still shown below.
              </p>
            </div>
          )}

          {result && (
            <Results
              result={result}
              fmt={fmt}
              isRefreshing={run.isPending}
              hasUnrunChanges={hasUnrunChanges}
            />
          )}
        </div>
      </div>
    </div>
  );
};

function readinessNotes(r: ScenarioReadiness | undefined): string[] {
  if (!r) return [];
  const plural = (n: number) => (n === 1 ? " has" : "s have");
  return [
    r.forecast_stale && r.forecast_age_days != null
      ? `The forecast completed ${Math.round(r.forecast_age_days)} days ago — older than the 14-day limit used for decisions.`
      : null,
    r.skus_missing_stock.length
      ? `${r.skus_missing_stock.length} SKU${plural(r.skus_missing_stock.length)} no recorded stock and start from zero on hand.`
      : null,
    r.skus_stale_stock.length
      ? `${r.skus_stale_stock.length} SKU${plural(r.skus_stale_stock.length)} stock older than 30 days.`
      : null,
    r.skus_lead_time_assumed.length
      ? `${r.skus_lead_time_assumed.length} SKU${r.skus_lead_time_assumed.length === 1 ? " uses" : "s use"} the assumed ${r.assumed_lead_time_days}-day lead time.`
      : null,
  ].filter((note): note is string => Boolean(note));
}

function Results({
  result,
  fmt,
  isRefreshing,
  hasUnrunChanges,
}: {
  result: SimulationResult;
  fmt: MoneyFmt;
  isRefreshing: boolean;
  hasUnrunChanges: boolean;
}) {
  const i = result.impact;
  // Rank by margin lost when it can be valued, otherwise by units short.
  const worst = result.by_sku
    .filter((s) => (s.delta.gross_margin != null ? s.delta.gross_margin < 0 : s.delta.short_units > 0))
    .slice(0, 12);
  const valuation = result.valuation_coverage;
  const missingCost = valuation ? valuation.skus_total - valuation.skus_with_cost : 0;
  const missingPrice = valuation ? valuation.skus_total - valuation.skus_with_price : 0;
  const notes = readinessNotes(result.readiness);
  const coverage = result.stock_coverage;
  const estimated = coverage.skus_total - coverage.skus_with_recorded_stock;
  const impactSummary = buildImpactSummary(result, fmt);

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-heading text-[15px] font-semibold">{result.scenario.name}</h3>
          <Badge variant="primary">Baseline comparison</Badge>
          <Badge variant="default">{result.skus_simulated} SKUs</Badge>
          <Badge variant="default">{result.config.horizon_weeks} weeks</Badge>
          {result.readiness?.advisory && <Badge variant="warning">Advisory</Badge>}
          {isRefreshing && (
            <Badge variant="primary" dot>
              Updating
            </Badge>
          )}
        </div>

        {result.config.horizon_capped_reason && (
          <p className="mt-3 text-xs leading-relaxed text-content-muted">{result.config.horizon_capped_reason}</p>
        )}

        {notes.length > 0 && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            <p className="font-semibold">Advisory result — these inputs are stale, missing or assumed:</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {notes.map((note) => <li key={note}>{note}</li>)}
            </ul>
          </div>
        )}

        {(hasUnrunChanges || isRefreshing) && (
          <div
            className="mt-4 rounded-xl border border-line bg-surface-2 px-4 py-3 text-xs leading-relaxed text-content-muted"
            role="status"
            aria-live="polite"
          >
            {isRefreshing
              ? "Updating the comparison. The last successful result stays visible until the new run completes."
              : "Showing the last successful comparison. Run the simulation to apply your current lever changes."}
          </div>
        )}

        <div className="mt-4 rounded-2xl border border-line bg-surface-2 px-4 py-3.5">
          <p className="text-[11px] font-bold uppercase tracking-widest text-[var(--accent)]">
            Impact summary
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-content">{impactSummary}</p>
        </div>

        <InventoryComparison result={result} />

        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Impact
            label="Fill rate"
            value={`${i.fill_rate_pts > 0 ? "+" : ""}${i.fill_rate_pts.toFixed(1)} pts`}
            good={i.fill_rate_pts >= 0}
            detail={`${(result.baseline.fill_rate * 100).toFixed(1)}% → ${(result.result.fill_rate * 100).toFixed(1)}%`}
          />
          <Impact
            label="Gross margin"
            value={fmt(i.gross_margin)}
            good={i.gross_margin == null ? null : i.gross_margin >= 0}
            detail={i.gross_margin == null ? "Needs unit cost and price for every SKU" : `${fmt(result.baseline.gross_margin)} → ${fmt(result.result.gross_margin)}`}
          />
          <Impact
            label="Lost revenue"
            value={fmt(i.lost_revenue)}
            good={i.lost_revenue == null ? null : i.lost_revenue <= 0}
            detail={i.lost_revenue == null ? "Needs unit price for every SKU" : "Demand you could not have shipped"}
          />
          <Impact
            label="SKUs stocking out"
            value={`${i.skus_stocking_out > 0 ? "+" : ""}${i.skus_stocking_out}`}
            good={i.skus_stocking_out <= 0}
            detail={`${result.baseline.skus_stocking_out} → ${result.result.skus_stocking_out}`}
          />
          <Impact
            label="Purchase spend"
            value={fmt(i.purchase_spend)}
            good={i.purchase_spend == null ? null : i.purchase_spend <= 0}
            detail={i.purchase_spend == null ? "Needs unit cost for every SKU" : "Extra capital the scenario forces you to commit"}
          />
          <Impact
            label="Average stock held"
            value={`${i.avg_inventory_units > 0 ? "+" : ""}${Math.round(i.avg_inventory_units).toLocaleString()} u`}
            good={i.avg_inventory_units <= 0}
            detail="Across the whole horizon"
          />
        </div>

        {(missingCost > 0 || missingPrice > 0) && valuation && (
          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-line bg-surface-2 px-4 py-3">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-500" />
            <p className="text-xs leading-relaxed text-content-muted">
              {missingCost > 0 && `${missingCost} of ${valuation.skus_total} SKUs missing unit cost. `}
              {missingPrice > 0 && `${missingPrice} of ${valuation.skus_total} SKUs missing unit price. `}
              Money figures that depend on them are withheld rather than treated as zero; quantities
              above are unaffected.{" "}
              <Link to="/workspace/data-quality" className="font-semibold text-[var(--accent)] underline-offset-2 hover:underline">Fix in Data Quality</Link>
            </p>
          </div>
        )}

        {estimated > 0 && !result.readiness && (
          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-500/30 dark:bg-amber-500/10">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-500" />
            <p className="text-xs leading-relaxed text-amber-800 dark:text-amber-200">
              {estimated} of {coverage.skus_total} SKUs have no recorded stock position, so the twin
              starts them from zero on hand. Load inventory data for a truer picture.
            </p>
          </div>
        )}
      </Card>

      {worst.length > 0 && (
        <Card
          title="Where it hurts most"
          description={i.gross_margin == null ? "SKUs with units short under this scenario; margin is shown where it can be valued." : "SKUs ranked by margin lost under this scenario."}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-content-subtle">
                  <th className="px-3 py-2 font-semibold">SKU</th>
                  <th className="px-3 py-2 text-right font-semibold">Fill rate</th>
                  <th className="px-3 py-2 text-right font-semibold">Units short</th>
                  <th className="px-3 py-2 text-right font-semibold">Margin impact</th>
                  <th className="px-3 py-2 text-right font-semibold">First stockout</th>
                </tr>
              </thead>
              <tbody>
                {worst.map((s) => (
                  <tr key={s.sku_id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2 font-mono text-xs font-semibold">{s.sku_code}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <span className={s.delta.fill_rate < 0 ? "text-rose-600" : ""}>
                        {(s.scenario.fill_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {Math.round(s.scenario.short_units).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold tabular-nums text-rose-600">
                      {fmt(s.delta.gross_margin)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-content-muted">
                      {s.scenario.first_stockout_week === null
                        ? "—"
                        : `week ${s.scenario.first_stockout_week + 1}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

type InventoryPoint = {
  week: number;
  baseline: number;
  scenario: number;
  band: [number, number];
};

function buildImpactSummary(result: SimulationResult, fmt: MoneyFmt) {
  const { impact } = result;
  const fillRate =
    impact.fill_rate_pts < 0
      ? `fill rate falls ${Math.abs(impact.fill_rate_pts).toFixed(1)} points`
      : impact.fill_rate_pts > 0
        ? `fill rate improves ${impact.fill_rate_pts.toFixed(1)} points`
        : "fill rate is unchanged";
  const grossMargin =
    impact.gross_margin == null
      ? "gross margin cannot be valued because unit costs or prices are missing"
      : impact.gross_margin < 0
        ? `gross margin falls ${fmt(Math.abs(impact.gross_margin))}`
        : impact.gross_margin > 0
          ? `gross margin improves ${fmt(impact.gross_margin)}`
          : "gross margin is unchanged";
  const stockouts =
    impact.skus_stocking_out > 0
      ? `${impact.skus_stocking_out} more SKUs stock out`
      : impact.skus_stocking_out < 0
        ? `${Math.abs(impact.skus_stocking_out)} fewer SKUs stock out`
        : "the number of SKUs stocking out is unchanged";

  return `Compared with baseline, ${fillRate}, ${grossMargin}, and ${stockouts} over ${result.config.horizon_weeks} weeks.`;
}

const formatUnits = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

function InventoryTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: InventoryPoint }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  return (
    <div className="min-w-44 rounded-xl border border-line-strong bg-surface p-3 text-xs shadow-md">
      <p className="font-semibold text-content">Week {point.week}</p>
      <dl className="mt-2 space-y-1.5">
        <div className="flex justify-between gap-6">
          <dt className="text-content-subtle">Baseline</dt>
          <dd className="font-mono font-semibold text-content">
            {Math.round(point.baseline).toLocaleString()} u
          </dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt className="text-content-subtle">Scenario</dt>
          <dd className="font-mono font-semibold text-[var(--accent)]">
            {Math.round(point.scenario).toLocaleString()} u
          </dd>
        </div>
      </dl>
    </div>
  );
}

function InventoryComparison({ result }: { result: SimulationResult }) {
  const data = useMemo<InventoryPoint[]>(() => {
    const longestSeries = result.by_sku.reduce(
      (longest, sku) =>
        Math.max(longest, sku.weekly.on_hand.length, sku.weekly.baseline_on_hand.length),
      0,
    );
    const weeks = Math.max(result.config.horizon_weeks, longestSeries);

    return Array.from({ length: weeks }, (_, index) => {
      const baseline = result.by_sku.reduce(
        (total, sku) => total + (sku.weekly.baseline_on_hand[index] ?? 0),
        0,
      );
      const scenario = result.by_sku.reduce(
        (total, sku) => total + (sku.weekly.on_hand[index] ?? 0),
        0,
      );

      return {
        week: index + 1,
        baseline,
        scenario,
        band: [Math.min(baseline, scenario), Math.max(baseline, scenario)],
      };
    });
  }, [result]);

  const finalPoint = data[data.length - 1];
  const chartSummary = finalPoint
    ? `At week ${finalPoint.week}, baseline inventory is ${Math.round(finalPoint.baseline).toLocaleString()} units and scenario inventory is ${Math.round(finalPoint.scenario).toLocaleString()} units.`
    : "No weekly inventory comparison is available.";

  return (
    <figure className="mt-5 border-t border-line pt-5" aria-label="Baseline and scenario inventory comparison">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-heading text-sm font-semibold text-content">Inventory trajectory</h4>
          <p className="mt-0.5 text-xs text-content-subtle">
            Portfolio units on hand, baseline against scenario.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-content-muted" aria-hidden="true">
          <span className="inline-flex items-center gap-2">
            <span className="w-7 border-t border-dashed border-content-subtle" /> Baseline
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-px w-7 bg-[var(--accent)]" /> Scenario
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-2.5 w-7 rounded-sm bg-[var(--accent)] opacity-10" /> Difference
          </span>
        </div>
      </div>
      <figcaption className="sr-only">{chartSummary}</figcaption>
      <div className="mt-4" aria-hidden="true">
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={data} margin={{ top: 6, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="2 6" stroke="var(--line)" />
            <XAxis
              dataKey="week"
              tickFormatter={(week) => `W${week}`}
              tick={{ fontSize: 11, fill: "var(--text-subtle)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--line-strong)" }}
              minTickGap={24}
            />
            <YAxis
              tickFormatter={formatUnits}
              tick={{ fontSize: 11, fill: "var(--text-subtle)" }}
              tickLine={false}
              axisLine={false}
              width={48}
              domain={[0, (dataMax: number) => Math.ceil(dataMax * 1.08)]}
            />
            <Tooltip
              content={<InventoryTooltip />}
              cursor={{ stroke: "var(--line-strong)", strokeWidth: 1 }}
            />
            <Area
              type="linear"
              dataKey="band"
              stroke="none"
              fill="var(--accent)"
              fillOpacity={0.08}
              isAnimationActive={false}
              tooltipType="none"
            />
            <Line
              type="linear"
              dataKey="baseline"
              stroke="var(--text-subtle)"
              strokeWidth={1.25}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
              name="Baseline"
            />
            <Line
              type="linear"
              dataKey="scenario"
              stroke="var(--accent)"
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
              name="Scenario"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function Impact({
  label,
  value,
  detail,
  good,
}: {
  label: string;
  value: string;
  detail: string;
  /** null = the value is unknown, so it is neither good nor bad. */
  good: boolean | null;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface-2 p-4">
      <p className="text-[11px] font-bold uppercase tracking-widest text-content-subtle">{label}</p>
      <p
        className={`mt-1.5 flex items-center gap-1.5 font-heading text-xl font-bold tabular-nums ${
          good == null ? "text-content-subtle" : good ? "text-emerald-600" : "text-rose-600"
        }`}
      >
        {good == null ? null : good ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
        {value}
      </p>
      <p className="mt-1 text-xs text-content-subtle">{detail}</p>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  hint,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  hint?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 text-sm">
        <span className="min-w-0 font-medium text-content-muted">{label}</span>
        <span className="font-semibold tabular-nums text-content">
          {value > 0 && unit === "%" ? "+" : ""}
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 block w-full min-w-0 max-w-full accent-[var(--accent)]"
        aria-label={label}
      />
      {hint && <p className="mt-1 text-[11px] leading-snug text-content-subtle">{hint}</p>}
    </div>
  );
}
