import { useState } from "react";
import { MODULES } from "@/pages/landing/content";

/**
 * o9's homepage answers "what do I get" with a solutions taxonomy. This is the
 * equivalent, built from the routes that actually exist in App.tsx rather than
 * from a roadmap.
 */
export const ModuleGrid = () => {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section id="platform-modules" className="lc-section">
      <div className="lc-shell">
        <div className="lc-intro">
          <p className="lc-kicker">The platform</p>
          <h2 className="lc-h2">What you get on day one</h2>
          <p className="lc-lede">
            Every module below is part of the workspace, scoped to your industry.
            Select one to see what it does.
          </p>
        </div>

        <ul className="lc-module-grid">
          {MODULES.map((m) => (
            <li key={m.key}>
              <button
                type="button"
                aria-expanded={open === m.key}
                aria-controls={`module-detail-${m.key}`}
                className={open === m.key ? "is-active" : ""}
                onClick={() => setOpen(open === m.key ? null : m.key)}
              >
                <span className="lc-module-name">{m.name}</span>
                <span className="lc-module-blurb">{m.blurb}</span>
              </button>
              {open === m.key && (
                <p id={`module-detail-${m.key}`} className="lc-module-detail">
                  {m.detail}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};
