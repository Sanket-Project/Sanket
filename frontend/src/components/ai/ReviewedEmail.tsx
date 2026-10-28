import { useState } from "react";
import { Button } from "@/components/ui/Button";

export interface EmailPreview { subject: string; body: string; preview_token: string; language: string }

export function ReviewedEmail({ preview, send, pending, status }: {
  preview: EmailPreview;
  send: (message: { recipient: string; subject: string; body: string; delivery_key: string; confirm: true }) => void;
  pending: boolean;
  status: string;
}) {
  const [recipient, setRecipient] = useState("");
  const [subject, setSubject] = useState(preview.subject);
  const [body, setBody] = useState(preview.body);
  const [confirmed, setConfirmed] = useState(false);
  const [identity] = useState(() => crypto.randomUUID());
  const edited = subject !== preview.subject || body !== preview.body;
  return <div className="space-y-3 border-t border-line pt-4">
    <p className="text-xs text-content-muted">{edited ? "User-edited draft" : "Factual template"}. Confirm recipient details before sending. Changes you make are not engine-verified.</p>
    <label className="block text-sm">Verified recipient email<input className="input mt-1" type="email" autoComplete="off" value={recipient} onChange={(event) => { setRecipient(event.target.value); setConfirmed(false); }} /></label>
    <label className="block text-sm">Subject<input className="input mt-1" maxLength={200} value={subject} onChange={(event) => { setSubject(event.target.value); setConfirmed(false); }} /></label>
    <label className="block text-sm">Message body<textarea className="input mt-1 min-h-48" maxLength={40000} value={body} onChange={(event) => { setBody(event.target.value); setConfirmed(false); }} /></label>
    <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed the recipient, message, figures, and attachments and confirm sending this email.</label>
    <Button size="sm" disabled={!confirmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient) || !subject.trim() || !body.trim() || status === "sent" || status === "ambiguous"} loading={pending}
      onClick={() => send({ recipient, subject, body, delivery_key: identity, confirm: true })}>Confirm and send email</Button>
    {status && <p role="status" className="text-sm">{({ sent: "Email sent", unavailable: "Email delivery unavailable. Contact your administrator to configure SMTP.",
      failed: "Email delivery failed. Review the delivery state before retrying.", ambiguous: "Delivery status is uncertain. Ask an administrator to review it before sending again.",
      error: "The email could not be sent. The source or your permission may have changed; review a fresh draft." } as Record<string, string>)[status] ?? status}</p>}
  </div>;
}
