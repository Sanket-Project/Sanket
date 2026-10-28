import { useMutation } from "@tanstack/react-query";
import { aiApi, type SummaryFeature } from "@/api/ai";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";
import { useCommunicationPreferences } from "@/hooks/useCommunicationPreferences";

type SummaryProps = { feature: SummaryFeature; entityId?: string; connector?: string; contextKey?: string; runId?: string; label?: string; language?: string };

const COPY: Record<string, { generate: string; pending: string; unavailable: string; generated: string; source: string }> = {
  en: { generate: "Generate AI summary", pending: "Preparing summary…", unavailable: "AI summary unavailable. Your source data remains available.", generated: "AI-generated", source: "Source" },
  hi: { generate: "एआई सारांश बनाएँ", pending: "सारांश तैयार हो रहा है…", unavailable: "एआई सारांश उपलब्ध नहीं है। स्रोत डेटा उपलब्ध है।", generated: "एआई द्वारा निर्मित", source: "स्रोत" },
  te: { generate: "ఏఐ సారాంశం రూపొందించండి", pending: "సారాంశం సిద్ధమవుతోంది…", unavailable: "ఏఐ సారాంశం అందుబాటులో లేదు. మూల డేటా అందుబాటులో ఉంది.", generated: "ఏఐ రూపొందించినది", source: "మూలం" },
  ta: { generate: "செயற்கை நுண்ணறிவுச் சுருக்கம் உருவாக்கு", pending: "சுருக்கம் தயாராகிறது…", unavailable: "செயற்கை நுண்ணறிவுச் சுருக்கம் கிடைக்கவில்லை. மூலத் தரவு கிடைக்கிறது.", generated: "செயற்கை நுண்ணறிவால் உருவாக்கப்பட்டது", source: "ஆதாரம்" },
};
const sourceHref = (source: string) => /^\/(inventory|products|skus|forecasts|decisions|data-quality|integrations|onboarding|roi|scenarios|alerts|trends|dashboard)(\/[a-zA-Z0-9_-]+)*$/.test(source)
  ? source === "/dashboard" ? "/workspace" : source === "/onboarding" ? "/onboarding" : `/workspace${source}` : null;

export function AISummary({ feature, entityId, connector, contextKey, runId, label }: SummaryProps) {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const language = useCommunicationPreferences().data?.preferences.language ?? "en";
  // Identity in the key remounts the request state before any old answer can render.
  return <Summary key={`${scope}:${language}:${feature}:${entityId || ""}:${connector || ""}:${contextKey || ""}:${runId || ""}`} feature={feature} entityId={entityId} connector={connector} runId={runId} label={label} language={language} />;
}

function Summary({ feature, entityId, connector, runId, label, language = "en" }: SummaryProps) {
  const copy = COPY[language] ?? COPY.en;
  const request = useMutation({ mutationFn: () => language !== "en" ? aiApi.summary(feature, entityId, connector, runId, language) : runId ? aiApi.summary(feature, entityId, connector, runId) : aiApi.summary(feature, entityId, connector) });
  return <aside className="space-y-2 rounded-xl border border-line bg-surface p-3 text-sm" aria-label="AI summary">
    <Button size="sm" variant="ghost" onClick={() => request.mutate()} disabled={request.isPending}>{label || copy.generate}</Button>
    {request.isPending && <p role="status">{copy.pending}</p>}
    {(request.isError || (request.data && request.data.state !== "success")) && <p role="status">{copy.unavailable}</p>}
    {request.data?.state === "success" && <>
      <p className="text-xs text-content-subtle">{copy.generated}</p>
      {request.data.blocks.map((block, index) => {
        const source = block.sources[0]?.href;
        const href = source && sourceHref(source);
        return <div key={index}><p>{href ? <a className="underline decoration-dotted underline-offset-4" href={href}>{block.text}</a> : block.text}</p>
          {block.sources.slice(1).map((citation) => {
            const target = sourceHref(citation.href);
            return target ? <a key={citation.fact_id} className="mr-3 inline-block text-xs text-content-muted underline underline-offset-4" href={target}>{copy.source}: {citation.fact_id}</a> : null;
          })}
        </div>;
      })}
    </>}
  </aside>;
}
