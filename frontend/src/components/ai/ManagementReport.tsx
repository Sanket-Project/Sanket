import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/Button";
import { ReviewedEmail, type EmailPreview } from "./ReviewedEmail";
import { ArtifactSummary, type ArtifactSummaryValue } from "./ArtifactSummary";
import { useCommunicationPreferences } from "@/hooks/useCommunicationPreferences";

interface Preview extends EmailPreview { report: { snapshot: string; as_of: string; label: string }; summary?: ArtifactSummaryValue }

export function ManagementReport({ windowDays }: { windowDays: number }) {
  const scope = useAuthStore((state) => `${state.tenantId}:${state.userId}`);
  const preferences = useCommunicationPreferences();
  return <ReportForm key={`${scope}:${windowDays}:${preferences.data?.preferences.language ?? "en"}`} windowDays={windowDays} />;
}

function ReportForm({ windowDays }: { windowDays: number }) {
  const lifetime = useRef(new AbortController());
  useEffect(() => {
    if (lifetime.current.signal.aborted) lifetime.current = new AbortController();
    const controller = lifetime.current;
    return () => controller.abort();
  }, []);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState("");
  const [downloadError, setDownloadError] = useState(false);
  const role = useAuthStore((state) => state.role);
  const canSend = role === "owner" || role === "admin";
  const download = async () => {
    const signal = lifetime.current.signal;
    setDownloadError(false);
    try {
      const { data } = await apiClient.get("/export/roi.pdf", { params: { window_days: windowDays }, responseType: "blob", signal });
      if (signal.aborted) return;
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url; link.download = "sanket-roi.pdf"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { if (!signal.aborted) setDownloadError(true); }
  };
  const review = async () => {
    const signal = lifetime.current.signal;
    setPending(true); setStatus("");
    try { const result = await apiClient.post("/management/roi/preview", { window_days: windowDays }, { signal }); if (!signal.aborted) setPreview(result.data); }
    catch { if (!signal.aborted) setStatus("Report preview unavailable. Try again when the source is available."); }
    finally { if (!signal.aborted) setPending(false); }
  };
  return <section className="space-y-3 rounded-2xl border border-line bg-surface p-4">
    <div className="flex flex-wrap items-center gap-2"><Button variant="secondary" size="sm" onClick={() => void download()}>Download ROI PDF</Button>
      {canSend && <Button variant="ghost" size="sm" loading={pending && !preview} onClick={() => void review()}>Review report email</Button>}</div>
    <p className="text-xs text-content-subtle">A factual snapshot for the selected {windowDays}-day period. Modeled opportunities, approval estimates, and observed results stay separate.</p>
    {downloadError && <p role="alert">The PDF could not be downloaded.</p>}
    {preview && <><p className="text-xs text-content-muted">{preview.report.label} · {preview.report.as_of}. The report PDF will be attached.</p>
      <ArtifactSummary value={preview.summary} />
      <ReviewedEmail key={preview.preview_token} preview={preview} pending={pending} status={status} send={async (message) => {
        const signal = lifetime.current.signal;
        setPending(true); setStatus("");
        try { const result = await apiClient.post("/management/roi/email", { ...message, window_days: windowDays, language: preview.language, preview_token: preview.preview_token }, { signal }); if (!signal.aborted) setStatus(result.data.state); }
        catch { if (!signal.aborted) setStatus("error"); }
        finally { if (!signal.aborted) setPending(false); }
      }} /></>}
    {!preview && status && <p role="alert">{status}</p>}
  </section>;
}
