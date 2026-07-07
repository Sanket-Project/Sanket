import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, RefreshCw } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { PageLoader } from "@/components/ui/Spinner";
import { useIndustryStore } from "@/stores/industry";
import { industryApi } from "@/api/industry";

interface ScenarioInputs {
  demandShockPct: number;   // +/- percentage shift on p50
  priceChangePct: number;   // price change (affects elasticity)
  leadTimeDays: number;     // additional lead time days
}

const DEFAULT: ScenarioInputs = { demandShockPct: 0, priceChangePct: 0, leadTimeDays: 0 };

export const WhatIfScenarioPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const [inputs, setInputs] = useState<ScenarioInputs>(DEFAULT);
  const [applied, setApplied] = useState<ScenarioInputs>(DEFAULT);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["what-if-overview", industry],
    queryFn: () => industryApi.overview(industry),
  });

  if (isLoading || !overview) return <PageLoader />;

  // Build scenario forecast rows from a demo base + shock
  const demandMultiplier = 1 + applied.demandShockPct / 100;
  const horizonWeeks = overview.forecast_horizon_weeks ?? 12;
  const baseRows = Array.from({ length: horizonWeeks }).map((_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i * 7);
    const base = 4200 + Math.sin(i / 3) * 600;
    return {
      sku_id: "scenario",
      forecast_date: d.toISOString().slice(0, 10),
      p10: base * 0.75,
      p50: base,
      p90: base * 1.28,
    };
  });
  const scenarioRows = baseRows.map((r) => ({
    ...r,
    p10: r.p10 * demandMultiplier,
    p50: r.p50 * demandMultiplier,
    p90: r.p90 * demandMultiplier,
  }));

  const Slider = ({
    label, value, min, max, step, unit, onChange,
  }: {
    label: string; value: number; min: number; max: number; step: number; unit: string;
    onChange: (v: number) => void;
  }) => (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-slate-600 font-medium">{label}</span>
        <span className={`font-bold tabular-nums ${value > 0 ? "text-emerald-600" : value < 0 ? "text-red-500" : "text-slate-500"}`}>
          {value > 0 ? "+" : ""}{value}{unit}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-violet-600"
      />
      <div className="flex justify-between text-[10px] text-slate-400">
        <span>{min}{unit}</span><span>0</span><span>+{max}{unit}</span>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
          <FlaskConical size={14} /> What-if Scenario Planner
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">Simulate demand & supply shocks</h1>
        <p className="text-slate-500 mt-1">Adjust sliders to model scenarios — see forecast impact in real time</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls */}
        <Card title="Scenario inputs" description="Drag to configure shock parameters">
          <div className="space-y-6">
            <Slider
              label="Demand shock"
              value={inputs.demandShockPct}
              min={-50} max={50} step={5} unit="%"
              onChange={(v) => setInputs((s) => ({ ...s, demandShockPct: v }))}
            />
            <Slider
              label="Price change"
              value={inputs.priceChangePct}
              min={-30} max={30} step={5} unit="%"
              onChange={(v) => setInputs((s) => ({ ...s, priceChangePct: v }))}
            />
            <Slider
              label="Additional lead time"
              value={inputs.leadTimeDays}
              min={0} max={60} step={5} unit=" days"
              onChange={(v) => setInputs((s) => ({ ...s, leadTimeDays: v }))}
            />
            <button
              onClick={() => setApplied({ ...inputs })}
              className="w-full flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold py-2.5 rounded-xl transition-colors"
            >
              <RefreshCw size={14} /> Apply scenario
            </button>
            <button
              onClick={() => { setInputs(DEFAULT); setApplied(DEFAULT); }}
              className="w-full text-sm text-slate-400 hover:text-slate-600 transition-colors"
            >
              Reset to baseline
            </button>
          </div>
        </Card>

        {/* Forecast comparison */}
        <Card className="lg:col-span-2" title="Baseline vs. scenario" description={`Demand shock: ${applied.demandShockPct > 0 ? "+" : ""}${applied.demandShockPct}% · Price: ${applied.priceChangePct > 0 ? "+" : ""}${applied.priceChangePct}% · Lead time: +${applied.leadTimeDays}d`}>
          <div className="space-y-4">
            <ForecastChart rows={baseRows} accent="#94a3b8" />
            <div className="border-t border-slate-100 pt-4">
              <p className="text-xs text-violet-600 font-semibold uppercase tracking-wide mb-2">Scenario</p>
              <ForecastChart rows={scenarioRows} accent="#7c3aed" />
            </div>
          </div>
        </Card>
      </div>

      {/* Impact summary */}
      <Card title="Scenario impact summary">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          {[
            { label: "Demand shift", value: `${applied.demandShockPct > 0 ? "+" : ""}${applied.demandShockPct}%`, color: applied.demandShockPct > 0 ? "text-emerald-600" : applied.demandShockPct < 0 ? "text-red-500" : "text-slate-500" },
            { label: "Price change", value: `${applied.priceChangePct > 0 ? "+" : ""}${applied.priceChangePct}%`, color: "text-slate-700" },
            { label: "Extra lead time", value: `${applied.leadTimeDays} days`, color: applied.leadTimeDays > 14 ? "text-red-500" : "text-slate-700" },
            { label: "Est. demand multiplier", value: `×${demandMultiplier.toFixed(2)}`, color: "text-violet-600" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-400 mb-1">{label}</p>
              <p className={`text-lg font-bold ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
