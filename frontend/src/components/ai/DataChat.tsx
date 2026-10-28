import { useEffect, useRef, useState } from "react";
import { aiInteractiveApi, type DataAnswer } from "@/api/aiInteractive";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";
import type { SummaryLanguage } from "@/api/communications";
import { useCommunicationPreferences } from "@/hooks/useCommunicationPreferences";

function unavailableMessage(answer: DataAnswer) {
  if (answer.state === "disabled") return "Sanket AI is turned off for this workspace. An owner or admin can enable data questions in Settings > AI assistance.";
  if (answer.state === "policy_blocked" && answer.reason === "sharing_disabled") return "Data questions require aggregate data sharing. An owner or admin can enable it in Settings > AI assistance.";
  return "AI answer unavailable. Open the source pages to review your data.";
}

type Exchange = { question: string; answer: DataAnswer };
const allowedSources = new Set(["/dashboard", "/inventory", "/forecasts", "/trends", "/skus", "/products"]);

export function DataChat() {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const userId = useAuthStore((s) => s.userId);
  const preferences = useCommunicationPreferences();
  const language = preferences.data?.preferences.language ?? "en";
  return userId ? <Chat key={`${scope}:${language}`} language={language} /> : null;
}

function Chat({ language }: { language: SummaryLanguage }) {
  const [text, setText] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const cancel = () => { controller.current?.abort(); setPending(false); };
  const ask = async () => {
    cancel();
    const request = new AbortController();
    controller.current = request;
    const question = text.trim();
    setPending(true); setError(false);
    try {
      const answer = await aiInteractiveApi.question(question, request.signal, language);
      if (request.signal.aborted) return;
      setHistory((previous) => [...previous.slice(-7), { question, answer }]); setText("");
    } catch { if (!request.signal.aborted) setError(true); }
    finally { if (!request.signal.aborted) setPending(false); }
  };
  return <details className="mb-4 rounded-2xl border border-line bg-surface p-4 text-sm" onToggle={(event) => { if (!event.currentTarget.open) cancel(); }}>
    <summary className="cursor-pointer font-semibold text-content focus-visible:outline-accent">Sanket AI</summary>
    <div className="mt-3 space-y-3">
      <p className="text-content-subtle">Read-only answers from sales, inventory, catalogue, trends and saved forecasts. Questions stay in this session. Each answer includes its source.</p>
      <div role="log" aria-live="polite" aria-label="Data answers" className="max-h-80 space-y-3 overflow-y-auto">
        {history.map(({ question, answer }, index) => <article key={index} className="space-y-2 rounded-xl border border-line p-3">
          <p className="font-medium">{question}</p>
          {answer.state === "success" ? <><p className="text-xs text-content-subtle">AI-generated</p>{answer.blocks.map((block, i) => <div key={i}><p>{block.text}</p><div className="flex flex-wrap gap-3">{block.sources.filter((source) => allowedSources.has(source.href) || /^\/skus\/[0-9a-f-]{36}$/.test(source.href)).map((source) => <a key={source.fact_id} className="text-xs text-accent underline underline-offset-4" href={source.href === "/dashboard" ? "/workspace" : `/workspace${source.href}`}>Source: {source.href.slice(1)}</a>)}</div></div>)}</> : <p>{answer.state === "no_data" ? answer.message || "I don't have data for that in this workspace." : unavailableMessage(answer)}</p>}
        </article>)}
      </div>
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); if (!pending && text.trim().length >= 3) void ask(); }}>
        <label className="block space-y-1"><span>Question about your data</span><textarea className="input min-h-20 w-full" maxLength={1500} required minLength={3} disabled={pending} value={text} onChange={(e) => setText(e.target.value)} /></label>
        <div className="flex flex-wrap gap-2"><Button size="sm" type="submit" disabled={pending || text.trim().length < 3}>Ask question</Button>
          {pending && <Button size="sm" type="button" variant="ghost" onClick={cancel}>Cancel question</Button>}
          <Button size="sm" type="button" variant="ghost" onClick={() => { cancel(); setHistory([]); setText(""); setError(false); }}>Clear conversation</Button>
        </div>
      </form>
      {pending && <p role="status">Reading your workspace sources…</p>}
      {error && <p role="alert">AI answer unavailable. Try again or open the source pages.</p>}
    </div>
  </details>;
}
