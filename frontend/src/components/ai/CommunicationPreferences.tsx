import { useCommunicationPreferences } from "@/hooks/useCommunicationPreferences";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { communicationsApi, type CommunicationStatus, type SummaryLanguage } from "@/api/communications";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";


export function CommunicationPreferences() {
  const query = useCommunicationPreferences();
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  if (query.isPending) return <p role="status">Loading communication preferences…</p>;
  if (query.isError || !query.data) return <p role="alert">Communication preferences unavailable.</p>;
  return <PreferencesForm key={`${scope}:${JSON.stringify(query.data.preferences)}`} data={query.data} />;
}

function PreferencesForm({ data }: { data: CommunicationStatus }) {
  const [draft, setDraft] = useState(data.preferences);
  const client = useQueryClient();
  const save = useMutation({ mutationFn: () => communicationsApi.save(draft), onSuccess: () => {
    void client.invalidateQueries({ queryKey: ["communication-preferences"] });
    void client.invalidateQueries({ queryKey: ["ai-summary"] });
  } });
  return <section className="space-y-4 rounded-2xl border border-line bg-surface p-5">
    <h2 className="font-heading text-lg text-content">Language and weekly email</h2>
    <p className="text-sm text-content-subtle">Your preferences follow your account. Weekly summaries use your account email and the current workspace’s approved engine facts.</p>
    <label className="block text-sm">Summary language<select aria-label="Summary language" className="input mt-1" value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value as SummaryLanguage })}>
      <option value="en">English</option><option value="hi">हिन्दी</option><option value="te">తెలుగు</option><option value="ta">தமிழ்</option>
    </select></label>
    <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={draft.weekly_enabled} onChange={(e) => setDraft({ ...draft, weekly_enabled: e.target.checked })} />Email me a weekly planning summary every Monday</label>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block text-sm">Timezone<input className="input mt-1" value={draft.timezone} placeholder="Asia/Kolkata" onChange={(e) => setDraft({ ...draft, timezone: e.target.value })} /></label>
      <label className="block text-sm">Local delivery hour<input className="input mt-1" type="number" min={0} max={23} value={draft.send_hour} onChange={(e) => setDraft({ ...draft, send_hour: Number(e.target.value) })} /></label>
    </div>
    <p className="text-xs text-content-subtle">AI assistance, weekly summaries, and aggregate sharing must also be enabled by a workspace administrator.</p>
    {!data.delivery_available && <p role="status" className="text-sm text-content-muted">Email delivery unavailable — an operator must configure TLS SMTP.</p>}
    {!data.scheduling_available && <p role="status" className="text-sm text-content-muted">Scheduling unavailable — the durable queue must be connected.</p>}
    {data.next_delivery && <p className="text-sm">Next planned summary: {new Intl.DateTimeFormat(draft.language, { dateStyle: "medium", timeStyle: "short", timeZone: data.preferences.timezone }).format(new Date(data.next_delivery))} ({data.preferences.timezone})</p>}
    {data.last_delivery && <p className="text-sm">Last delivery: {data.last_delivery.state}</p>}
    <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>Save communication preferences</Button>
    {save.isError && <p role="alert">Preferences could not be saved. Check the timezone and try again.</p>}
    {save.isSuccess && <p role="status">Communication preferences saved.</p>}
  </section>;
}
