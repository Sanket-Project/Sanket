import { useState } from "react";
import { SIGNALS } from "@/pages/landing/content";

/**
 * Names the outside data the engine reads and where each feed comes from.
 * A forecast that moves without a named cause is a number nobody trusts.
 */
export const SignalGrid = () => {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section id="signals" className="lc-section lc-section-alt">
      <div className="lc-shell">
        <div className="lc-intro">
          <p className="lc-kicker">Signals</p>
          <h2 className="lc-h2">Demand moves before your sales report does</h2>
          <p className="lc-lede">
            SANKET reads outside signals alongside your own history, so a change
            in the forecast arrives with a reason attached.
          </p>
        </div>

        <ul className="lc-signal-grid">
          {SIGNALS.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                aria-expanded={open === s.key}
                aria-controls={`signal-detail-${s.key}`}
                className={open === s.key ? "is-active" : ""}
                onClick={() => setOpen(open === s.key ? null : s.key)}
              >
                <span className="lc-signal-name">{s.name}</span>
                <span className="lc-signal-source">{s.source}</span>
              </button>
              {open === s.key && (
                <p id={`signal-detail-${s.key}`} className="lc-signal-feeds">
                  {s.feeds}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};
