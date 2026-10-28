import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aiApi, type AISettingsValue } from "@/api/ai";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";
import { ImportFormats } from "./ImportFormats";

const FEATURE_LABELS: Record<string, string> = {
  import_mapping: "Import column mapping", import_plan: "Smart import planning (multiple files)",
  onboarding: "Onboarding and connector help",
  data_quality: "Data-quality explanations", product_cleanup: "Product cleanup suggestions",
  decision_explanation: "Decision explanations", alert_explanation: "Alert and anomaly explanations",
  planning_brief: "Planning brief summary", industry_advice: "Industry advice",
  weekly_summary: "Weekly email summaries", roi_report: "ROI report summaries", supplier_draft: "Supplier draft summaries",
  scenario_interpretation: "Natural-language scenarios", scenario_explanation: "Scenario result explanations",
  data_qa_plan: "Read-only data questions", data_qa_answer: "Source-linked data answers",
};

export function AISettings() {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const query = useQuery({ queryKey: ["ai-settings", scope], queryFn: aiApi.settings });
  if (query.isPending) return <p role="status">Loading AI settings…</p>;
  if (!query.data || query.isError) return <p role="alert">AI settings unavailable.</p>;
  return <SettingsForm key={`${scope}:${JSON.stringify(query.data)}`} data={query.data} />;
}

function SettingsForm({ data }: { data: AISettingsValue }) {
  const [draft, setDraft] = useState(data);
  const [formatsOpen, setFormatsOpen] = useState(false);
  const client = useQueryClient();
  const save = useMutation({ mutationFn: () => aiApi.saveSettings({ enabled: draft.enabled, sharing: draft.sharing,
    tasks: draft.tasks, aggregate_context: draft.aggregate_context, product_names: draft.product_names }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["ai-settings"] }); } });
  return <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
    <h2 className="font-heading text-lg text-content">AI assistance</h2>
    <p className="text-sm text-content-subtle">DeepSeek receives only the data categories you enable. AI suggestions require review before changing data or sending a message.</p>
    <fieldset className="space-y-3" disabled={!data.can_manage || save.isPending}>
      <label className="flex items-center gap-2"><input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />Enable AI in this workspace</label>
      <label className="block">Import data sharing<select className="input" value={draft.sharing} onChange={(e) => setDraft({ ...draft, sharing: e.target.value as AISettingsValue["sharing"] })}>
        <option value="disabled">Disabled — no AI requests</option><option value="headers_only">Column headers only</option><option value="redacted_samples">Headers and redacted type examples</option>
      </select></label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={draft.aggregate_context} onChange={(e) => setDraft({ ...draft, aggregate_context: e.target.checked })} />Share aggregate engine facts for summaries and questions</label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={draft.product_names} onChange={(e) => setDraft({ ...draft, product_names: e.target.checked })} />Share screened product names for cleanup suggestions</label>
      <div className="grid gap-2 sm:grid-cols-2">{Object.entries(draft.tasks).filter(([task]) => task in FEATURE_LABELS).map(([task, enabled]) => <label className="flex items-center gap-2 text-sm" key={task}><input type="checkbox" checked={enabled} onChange={(e) => setDraft({ ...draft, tasks: { ...draft.tasks, [task]: e.target.checked } })} />{FEATURE_LABELS[task]}</label>)}</div>
      <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>Save AI settings</Button>
    </fieldset>
    {!data.can_manage && <p className="text-sm">An owner or admin can change AI settings.</p>}
    {save.isError && <p role="alert">AI settings could not be saved.</p>}
    {save.isSuccess && <p role="status">AI settings saved.</p>}
    {data.can_manage && <Button size="sm" variant="ghost" onClick={() => setFormatsOpen(!formatsOpen)}>Manage saved import formats</Button>}
    {formatsOpen && <ImportFormats />}
  </section>;
}
