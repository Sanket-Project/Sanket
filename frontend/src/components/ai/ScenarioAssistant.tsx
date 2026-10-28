import { useEffect, useRef, useState } from "react";
import { aiInteractiveApi, type Interpretation, type ScenarioAssumptions, type ScenarioField } from "@/api/aiInteractive";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";
import type { SummaryLanguage } from "@/api/communications";
import { useCommunicationPreferences } from "@/hooks/useCommunicationPreferences";

const FIELDS: Record<ScenarioField, { label: string; min: number; max: number; step: number }> = {
  demand_shock_pct: { label: "Demand change (%)", min: -95, max: 500, step: 0.1 },
  price_change_pct: { label: "Price change (%)", min: -90, max: 300, step: 0.1 },
  cost_change_pct: { label: "Cost change (%)", min: -90, max: 300, step: 0.1 },
  lead_time_delta_days: { label: "Lead-time change (days)", min: -60, max: 365, step: 1 },
  supplier_outage_weeks: { label: "Supplier outage (weeks)", min: 0, max: 52, step: 1 },
};

export function ScenarioAssistant({ onApply }: { onApply: (values: ScenarioAssumptions) => void }) {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const preferences = useCommunicationPreferences();
  const language = preferences.data?.preferences.language ?? "en";
  return <Assistant key={`${scope}:${language}`} language={language} onApply={onApply} />;
}

function Assistant({ onApply, language }: { onApply: (values: ScenarioAssumptions) => void; language: SummaryLanguage }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Interpretation | null>(null);
  const [values, setValues] = useState<ScenarioAssumptions>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [applied, setApplied] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const interpret = async () => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setBusy(true); setResult(null); setError(false); setApplied(false);
    try {
      const next = await aiInteractiveApi.interpret(text, request.signal, language);
      if (request.signal.aborted) return;
      setResult(next); setValues(next.assumptions || {});
    } catch { if (!request.signal.aborted) setError(true); }
    finally { if (!request.signal.aborted) setBusy(false); }
  };
  return <section aria-label="Scenario interpretation" className="space-y-3 rounded-2xl border border-line bg-surface p-4">
    <h2 className="font-semibold text-content">Describe a what-if</h2>
    <p className="text-sm text-content-subtle">For example: “Demand increases by 20% and lead time increases by 2 weeks.” Review assumptions, apply them to the controls, then choose Run simulation.</p>
    <label className="block space-y-1 text-sm"><span>Describe a scenario</span>
      <textarea className="input min-h-20 w-full" maxLength={1500} value={text} disabled={busy} onChange={(e) => { setText(e.target.value); setResult(null); setApplied(false); }} />
    </label>
    <Button size="sm" variant="secondary" onClick={() => void interpret()} disabled={busy || text.trim().length < 3}>Interpret assumptions</Button>
    {busy && <p role="status" className="text-sm">Interpreting assumptions…</p>}
    {(error || (result && !["success", "needs_clarification"].includes(result.state))) && <p role="status" className="text-sm">AI interpretation unavailable. You can still use the scenario controls.</p>}
    {result && ["success", "needs_clarification"].includes(result.state) && <div className="space-y-3 text-sm">
      <p className="text-xs text-content-subtle">AI-generated selection · numeric values come from your text</p>
      {result.evidence.map((item) => <p key={item.field} className="border-l-2 border-accent pl-3">{item.span}</p>)}
      {result.unresolved?.map((message, i) => <p key={i} role="status">{message}</p>)}
      <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); onApply(values); setApplied(true); }}>
        <div className="grid gap-3 sm:grid-cols-2">{(Object.keys(values) as ScenarioField[]).filter((field) => field in FIELDS).map((field) => <label key={field} className="block space-y-1"><span>{FIELDS[field].label}</span>
          <input className="input w-full" type="number" required min={FIELDS[field].min} max={FIELDS[field].max} step={FIELDS[field].step} value={values[field] ?? ""}
            onChange={(e) => { setValues({ ...values, [field]: e.target.value === "" ? undefined : Number(e.target.value) }); setApplied(false); }} />
        </label>)}</div>
        {Object.keys(values).length > 0 && <Button size="sm" type="submit">Apply reviewed assumptions</Button>}
      </form>
      {applied && <p role="status">Assumptions applied. Review the controls and choose Run simulation.</p>}
    </div>}
  </section>;
}
