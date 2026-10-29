import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { ArrowRight, Sparkles } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";

export const PlanningHero = ({ onGenerate, generating, brief, actions }: { onGenerate: () => void; generating: boolean; brief?: ReactNode; actions?: ReactNode }) => (
  <section className="planning-hero" aria-label="SANKET planning">
    <img src={`${import.meta.env.BASE_URL}images/planning-hero.webp`} alt="" width={1200} height={654} className="planning-hero-art" />
    <div className="planning-hero-copy">
      <p className="mb-3 inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-content-muted">SANKET AI <Sparkles size={14} className="text-accent" /></p>
      <h1 className="font-heading text-content">Turn demand signals<br className="hidden sm:block" /> into confident decisions.</h1>
      <div className="mt-3 max-w-xl text-sm leading-relaxed text-content-muted">{brief ?? <p>Forecast demand. Understand your stock. Make the next decision with a clearer view.</p>}</div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <Button onClick={onGenerate} loading={generating} icon={<Sparkles size={15} />} className="!rounded-full">Generate forecast</Button>
        <Link to="/workspace/trends" className="inline-flex items-center gap-2 text-xs font-semibold text-accent">View latest insights <ArrowRight size={14} /></Link>
        {actions}
      </div>
    </div>
  </section>
);
