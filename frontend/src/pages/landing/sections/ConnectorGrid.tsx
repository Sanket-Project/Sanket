import { useMemo, useState } from "react";
import { Search } from "@/components/ui/icons";
import {
  CONNECTOR_CATEGORIES,
  CONNECTORS,
  LIVE_CONNECTOR_COUNT,
  TOTAL_CONNECTOR_COUNT,
  type Availability,
} from "@/pages/landing/content";

const BADGE: Record<Availability, string> = {
  live: "Live",
  beta: "Beta",
  planned: "Coming soon",
};

const ALL = "All";

/**
 * Availability is shown per connector rather than rolled into one headline
 * number. Six of the forty-two work today; advertising the catalog size as if
 * it were the integration count is exactly the claim this page must not make.
 */
export const ConnectorGrid = () => {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(ALL);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return CONNECTORS.filter(
      (c) =>
        (category === ALL || c.category === category) &&
        (q === "" || c.name.toLowerCase().includes(q)),
    );
  }, [query, category]);

  return (
    <section id="integrations" className="lc-section lc-section-alt">
      <div className="lc-shell">
        <div className="lc-intro">
          <p className="lc-kicker">Integrations</p>
          <h2 className="lc-h2">Works on top of the stack you already run</h2>
          <p className="lc-lede">
            {LIVE_CONNECTOR_COUNT} live today, {TOTAL_CONNECTOR_COUNT} in the
            catalog. Start with a file or a database and add sources as you go —
            there is no migration step.
          </p>
        </div>

        <div className="lc-connector-controls">
          <label className="lc-search">
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              aria-label="Search connectors"
              placeholder="Search connectors"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>

          <div className="lc-chips">
            {[ALL, ...CONNECTOR_CATEGORIES].map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={category === c}
                className={category === c ? "is-active" : ""}
                onClick={() => setCategory(c)}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {shown.length === 0 ? (
          <p className="lc-body">No connectors match that search.</p>
        ) : (
          <ul className="lc-connector-grid">
            {shown.map((c) => (
              <li key={c.name} className={`lc-connector is-${c.availability}`}>
                <span className="lc-connector-name">{c.name}</span>
                <span className="lc-connector-meta">{c.category}</span>
                <span className={`lc-badge is-${c.availability}`}>{BADGE[c.availability]}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
};
