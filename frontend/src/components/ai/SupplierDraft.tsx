import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/Button";
import { ReviewedEmail, type EmailPreview } from "./ReviewedEmail";
import { ArtifactSummary, type ArtifactSummaryValue } from "./ArtifactSummary";
import { useCommunicationPreferences } from "@/hooks/useCommunicationPreferences";

interface Preview extends EmailPreview { quantity: number; currency: string; revision: string; whatsapp_text: string; source: string; summary?: ArtifactSummaryValue }

export function SupplierDraft({ decisionId }: { decisionId: string }) {
  const scope = useAuthStore((state) => `${state.tenantId}:${state.userId}`);
  const preferences = useCommunicationPreferences();
  return <DraftForm key={`${scope}:${decisionId}:${preferences.data?.preferences.language ?? "en"}`} decisionId={decisionId} />;
}

function DraftForm({ decisionId }: { decisionId: string }) {
  const lifetime = useRef(new AbortController());
  useEffect(() => {
    if (lifetime.current.signal.aborted) lifetime.current = new AbortController();
    const controller = lifetime.current;
    return () => controller.abort();
  }, []);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState("");
  const [copied, setCopied] = useState(false);
  const role = useAuthStore((state) => state.role);
  const canSend = role === "owner" || role === "admin";
  return <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
    <Button size="sm" variant="secondary" loading={pending && !preview} onClick={async () => {
      const signal = lifetime.current.signal;
      setPending(true); setStatus("");
      try { const result = await apiClient.post(`/management/supplier/${decisionId}/preview`, {}, { signal }); if (!signal.aborted) setPreview(result.data); }
      catch { if (!signal.aborted) setStatus("Draft unavailable. An accepted, unexpired purchase-order recommendation is required."); }
      finally { if (!signal.aborted) setPending(false); }
    }}>Prepare supplier draft</Button>
    {preview && <><p className="text-sm text-content-muted">Approved quantity: {preview.quantity.toLocaleString()} · {preview.currency}. Supplier contact is required; it is never inferred.</p>
      <ArtifactSummary value={preview.summary} />
      <label className="block text-sm">WhatsApp text<textarea className="input mt-1 min-h-28" readOnly value={preview.whatsapp_text} /></label>
      <Button variant="ghost" size="sm" onClick={async () => {
        try { await navigator.clipboard.writeText(preview.whatsapp_text); setCopied(true); }
        catch { setStatus("Copy unavailable. Select and copy the WhatsApp text above."); }
      }}>{copied ? "Copied" : "Copy WhatsApp text"}</Button>
      {canSend && <ReviewedEmail key={preview.preview_token} preview={preview} pending={pending} status={status} send={async (message) => {
        const signal = lifetime.current.signal;
        setPending(true); setStatus("");
        try { const result = await apiClient.post(`/management/supplier/${decisionId}/email`, { ...message, language: preview.language, preview_token: preview.preview_token }, { signal }); if (!signal.aborted) setStatus(result.data.state); }
        catch { if (!signal.aborted) setStatus("error"); }
        finally { if (!signal.aborted) setPending(false); }
      }} />}
    </>}
    {!preview && status && <p role="alert">{status}</p>}
  </section>;
}
