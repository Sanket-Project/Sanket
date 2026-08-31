import { useState } from "react";
import { Cpu, Layers, Pill, Sprout, Wrench, type AppIcon } from "@/components/ui/icons";
import { INDUSTRY_DETAIL } from "@/pages/landing/content";
import type { IndustryCode } from "@/types/api";

const ICONS: Record<IndustryCode, AppIcon> = {
  fashion: Layers,
  electronics: Cpu,
  pharma: Pill,
  agrocenter: Sprout,
  hardware: Wrench,
};

const ORDER: IndustryCode[] = ["fashion", "electronics", "pharma", "agrocenter", "hardware"];

/**
 * The strongest section on the page, because the facts are specific and real:
 * each vertical plans on its own horizon at its own audit level, straight from
 * the backend's industry registry. A competitor can copy a claim about serving
 * many industries; they cannot copy "52 weeks at GxP audit level" unless their
 * engine actually does that.
 */
export const IndustryTabs = () => {
  const [active, setActive] = useState<IndustryCode>("fashion");
  const detail = INDUSTRY_DETAIL[active];

  return (
    <section id="industries" className="lc-section">
      <div className="lc-shell">
        <div className="lc-intro lc-intro-center">
          <p className="lc-kicker">Industries</p>
          <h2 className="lc-h2">One engine, fluent in your operation</h2>
          <p className="lc-lede">
            The reasoning stays the same. The horizon, the signals and the audit
            level change with what you sell.
          </p>
        </div>

        <div className="lc-tabs" role="tablist" aria-label="Industries">
          {ORDER.map((code) => {
            const Icon = ICONS[code];
            return (
              <button
                key={code}
                type="button"
                role="tab"
                aria-selected={active === code}
                aria-controls="lc-industry-panel"
                className={active === code ? "is-active" : ""}
                onClick={() => setActive(code)}
              >
                <Icon size={16} aria-hidden="true" />
                {INDUSTRY_DETAIL[code].label}
              </button>
            );
          })}
        </div>

        <div id="lc-industry-panel" role="tabpanel" className="lc-industry-panel">
          <dl className="lc-industry-specs">
            <div>
              <dt>Planning horizon</dt>
              <dd>{detail.horizonWeeks}-week</dd>
            </div>
            <div>
              <dt>Audit level</dt>
              <dd>{detail.auditLevel}</dd>
            </div>
            <div>
              <dt>Signals</dt>
              <dd>{detail.signals.join(" · ")}</dd>
            </div>
          </dl>

          <div className="lc-industry-card-stack">
            <article>
              <span className="lc-card-label">SANKET observes</span>
              <p>{detail.observes}</p>
            </article>
            <article>
              <span className="lc-card-label">It catches</span>
              <p>{detail.risk}</p>
            </article>
            <article>
              <span className="lc-card-label">You act</span>
              <p>{detail.action}</p>
            </article>
          </div>
        </div>
      </div>
    </section>
  );
};
