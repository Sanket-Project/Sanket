import { useState } from "react";
import { AISummary } from "./AISummary";

export function OnboardingHelper() {
  const [question, setQuestion] = useState("");
  return <section className="space-y-3 rounded-2xl border border-line bg-surface p-4">
    <h3 className="font-heading font-semibold">Understand your uploaded data</h3>
    <p className="text-sm text-content-subtle">Summarize coverage and missing inputs, or ask how to connect a source. Connector answers use the current catalog.</p>
    <label className="block text-sm">Connector question<input className="input" aria-label="Connector question" value={question} maxLength={80} placeholder="How do I connect Shopify?" onChange={(e) => setQuestion(e.target.value)} /></label>
    <AISummary feature="onboarding" connector={question || undefined} />
  </section>;
}
