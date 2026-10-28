export interface ArtifactSummaryValue { state: string; blocks: Array<{ text: string; sources: Array<{ fact_id: string; href: string }> }> }

export function ArtifactSummary({ value }: { value?: ArtifactSummaryValue }) {
  if (!value || value.state === "disabled") return null;
  if (value.state !== "success") return <p role="status" className="text-xs text-content-muted">AI summary unavailable. The factual artifact remains available.</p>;
  return <div className="space-y-2 rounded-xl border border-line bg-surface-2 p-3">
    <p className="text-xs font-semibold text-content-muted">AI-generated summary</p>
    {value.blocks.map((block, index) => <div key={index}><p className="text-sm">{block.text}</p><div className="flex flex-wrap gap-2">{block.sources.map((source) => <a className="text-xs text-accent underline" key={source.fact_id} href={`/workspace${source.href}`}>Source: {source.fact_id.replaceAll("_", " ")}</a>)}</div></div>)}
  </div>;
}
