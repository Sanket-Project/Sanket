import { useMutation } from "@tanstack/react-query";
import { aiApi, type SummaryFeature } from "@/api/ai";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/stores/auth";

export function AISummary({ feature, entityId, connector }: { feature: SummaryFeature; entityId?: string; connector?: string }) {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  // Identity in the key remounts the request state before any old answer can render.
  return <Summary key={`${scope}:${feature}:${entityId || ""}:${connector || ""}`} feature={feature} entityId={entityId} connector={connector} />;
}

function Summary({ feature, entityId, connector }: { feature: SummaryFeature; entityId?: string; connector?: string }) {
  const request = useMutation({ mutationFn: () => aiApi.summary(feature, entityId, connector) });
  return <aside className="space-y-2 rounded-xl border border-line bg-surface p-3 text-sm" aria-label="AI summary">
    <Button size="sm" variant="ghost" onClick={() => request.mutate()} disabled={request.isPending}>Generate AI summary</Button>
    {request.isPending && <p role="status">Preparing summary…</p>}
    {(request.isError || (request.data && request.data.state !== "success")) && <p role="status">AI summary unavailable. Your source data remains available.</p>}
    {request.data?.state === "success" && <>
      <p className="text-xs text-content-subtle">AI-generated</p>
      {request.data.blocks.map((block, index) => {
        const source = block.sources[0]?.href;
        const safe = source && /^\/(inventory|products|skus|forecasts|decisions|data-quality|integrations|onboarding|roi|scenarios|alerts|trends|dashboard)(\/[a-zA-Z0-9_-]+)*$/.test(source);
        return <p key={index}>{safe ? <a className="underline decoration-dotted underline-offset-4" href={`/workspace${source}`}>{block.text}</a> : block.text}</p>;
      })}
    </>}
  </aside>;
}
