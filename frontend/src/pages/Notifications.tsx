import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { AlertTriangle, MessageCircle, Plus, Send, Trash2 } from "@/components/ui/icons";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PageLoader } from "@/components/ui/Spinner";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { getErrorMessage } from "@/utils/errors";
import { notificationsApi, type WhatsAppConfig, type WhatsAppRecipient } from "@/api/notifications";

const HOURS = Array.from({ length: 24 }, (_, i) => i);

/**
 * WhatsApp digest settings.
 *
 * Most SME owners will never open a dashboard, so the morning message *is* the
 * product for them. The preview pane is deliberately front and centre: it
 * renders the exact body from live data, which is the only way to tune the
 * thresholds without spamming a real phone.
 */
export const NotificationsPage = () => {
  const industry = useWorkspaceIndustry();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<WhatsAppConfig | null>(null);
  const [newPhone, setNewPhone] = useState("");
  const [newName, setNewName] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["whatsapp-config"],
    queryFn: notificationsApi.getWhatsApp,
  });

  const { data: preview, isFetching: previewing } = useQuery({
    queryKey: ["whatsapp-preview", industry],
    queryFn: notificationsApi.previewDigest,
  });

  useEffect(() => {
    if (data?.config && draft === null) setDraft(data.config);
  }, [data, draft]);

  const save = useMutation({
    mutationFn: notificationsApi.updateWhatsApp,
    onSuccess: (res) => {
      setDraft(res.config);
      queryClient.invalidateQueries({ queryKey: ["whatsapp-config"] });
      toast.success("Saved");
    },
    onError: (e) => toast.error(getErrorMessage(e)),
  });

  const sendTest = useMutation({
    mutationFn: () => notificationsApi.sendTest({ confirm: true }),
    onSuccess: (res) => {
      if (res.sent) toast.success("Digest sent");
      else {
        const err = res.results?.find((r) => !r.success)?.error;
        toast.error(err ?? "Not delivered — see the delivery status above");
      }
    },
    onError: (e) => toast.error(getErrorMessage(e)),
  });

  if (isLoading || !data || !draft) return <PageLoader />;

  const set = <K extends keyof WhatsAppConfig>(key: K, value: WhatsAppConfig[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const addRecipient = () => {
    const phone = newPhone.trim();
    if (!phone) return;
    const next: WhatsAppRecipient = { phone, name: newName.trim() || null, role: null };
    set("recipients", [...draft.recipients, next]);
    setNewPhone("");
    setNewName("");
  };

  const removeRecipient = (phone: string) =>
    set("recipients", draft.recipients.filter((r) => r.phone !== phone));

  const dirty = JSON.stringify(draft) !== JSON.stringify(data.config);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-emerald-600">
          <MessageCircle size={14} /> WhatsApp
        </div>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">The morning digest</h1>
        <p className="mt-1 max-w-2xl text-content-subtle">
          One message a day with what to order and what it is worth. No dashboard required.
        </p>
      </div>

      {!data.delivery.configured && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-500/30 dark:bg-amber-500/10">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
          <div>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
              Delivery is not connected yet
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-amber-700 dark:text-amber-300">
              {data.delivery.detail} Everything else works — the digest below is built from your live
              data, so you can tune it now and switch delivery on when the API credentials land.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <Card title="Recipients" description="Owners and buyers who should get the digest.">
            <div className="space-y-2">
              {draft.recipients.length === 0 && (
                <p className="text-sm text-content-subtle">No numbers added yet.</p>
              )}
              {draft.recipients.map((r) => (
                <div
                  key={r.phone}
                  className="flex items-center justify-between rounded-xl border border-line bg-surface-2 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm font-semibold text-content">{r.phone}</p>
                    {r.name && <p className="truncate text-xs text-content-subtle">{r.name}</p>}
                  </div>
                  <button
                    onClick={() => removeRecipient(r.phone)}
                    className="shrink-0 rounded-lg p-1.5 text-content-subtle transition-colors hover:bg-rose-500/10 hover:text-rose-600"
                    aria-label={`Remove ${r.phone}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap items-end gap-2">
              <div className="min-w-[150px] flex-1">
                <Input
                  name="whatsapp-phone"
                  label="Phone"
                  placeholder="98765 43210"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                />
              </div>
              <div className="min-w-[130px] flex-1">
                <Input
                  name="whatsapp-name"
                  label="Name (optional)"
                  placeholder="Rajesh"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </div>
              <Button variant="secondary" icon={<Plus size={15} />} onClick={addRecipient}>
                Add
              </Button>
            </div>
            <p className="mt-2 text-xs text-content-subtle">
              Indian numbers can be entered any way you like — +91 is added automatically.
            </p>
          </Card>

          <Card title="When and what" description="Tuning that decides whether people keep reading.">
            <div className="space-y-5">
              <label className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-content">Send the daily digest</p>
                  <p className="text-xs text-content-subtle">
                    Skipped automatically on days with nothing to act on.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(e) => set("enabled", e.target.checked)}
                  className="h-5 w-5 accent-[var(--accent)]"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-content-muted">Send at</span>
                <select
                  value={draft.send_hour}
                  onChange={(e) => set("send_hour", Number(e.target.value))}
                  className="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm"
                >
                  {HOURS.map((h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, "0")}:00 {draft.timezone}
                    </option>
                  ))}
                </select>
              </label>

              <div>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-medium text-content-muted">Minimum confidence</span>
                  <span className="font-semibold tabular-nums">{draft.min_confidence}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={draft.min_confidence}
                  onChange={(e) => set("min_confidence", Number(e.target.value))}
                  className="mt-2 w-full accent-[var(--accent)]"
                />
                <p className="mt-1 text-[11px] text-content-subtle">
                  Recommendations below this score stay in the app rather than on someone's phone.
                </p>
              </div>

              <div>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-medium text-content-muted">Items per message</span>
                  <span className="font-semibold tabular-nums">{draft.max_items}</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={20}
                  step={1}
                  value={draft.max_items}
                  onChange={(e) => set("max_items", Number(e.target.value))}
                  className="mt-2 w-full accent-[var(--accent)]"
                />
              </div>

              <label className="flex items-center justify-between gap-4">
                <span className="text-sm font-medium text-content">Include open shortage alerts</span>
                <input
                  type="checkbox"
                  checked={draft.include_alerts}
                  onChange={(e) => set("include_alerts", e.target.checked)}
                  className="h-5 w-5 accent-[var(--accent)]"
                />
              </label>
            </div>

            <div className="mt-6 flex gap-2">
              <Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate(draft)}>
                Save settings
              </Button>
              <Button
                variant="secondary"
                icon={<Send size={15} />}
                loading={sendTest.isPending}
                disabled={draft.recipients.length === 0}
                onClick={() => sendTest.mutate()}
              >
                Send me today's digest
              </Button>
            </div>
          </Card>
        </div>

        <Card
          title="Preview"
          description="Rendered from your live data — exactly what would be sent."
          action={
            preview && (
              <Badge variant={preview.would_send ? "success" : "default"}>
                {preview.characters} chars
              </Badge>
            )
          }
        >
          {previewing && !preview ? (
            <PageLoader />
          ) : (
            <div className="rounded-2xl bg-[#0b141a] p-4">
              <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-[#1f2c33] px-3.5 py-2.5">
                <pre className="whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed text-[#e9edef]">
                  {preview?.body ?? ""}
                </pre>
                <p className="mt-1.5 text-right text-[10px] text-[#8696a0]">
                  {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
            </div>
          )}

          {preview && !preview.would_send && (
            <p className="mt-3 text-xs leading-relaxed text-content-subtle">
              {preview.digest.empty_reason
                ? preview.digest.empty_reason
                : draft.recipients.length === 0
                  ? "Add a recipient to enable sending."
                  : "Turn the digest on to start sending."}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
};
