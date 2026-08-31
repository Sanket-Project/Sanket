const STEPS = [
  {
    num: "01",
    name: "Ingest",
    body: "Connect a storefront, a database or a spreadsheet. SANKET maps whatever you send into one canonical shape, and tells you what is missing rather than forecasting on top of the gaps.",
  },
  {
    num: "02",
    name: "Forecast",
    body: "Every SKU gets its own model selection and a confidence range, on the planning horizon your industry actually works to — twelve weeks in electronics, fifty-two in pharma.",
  },
  {
    num: "03",
    name: "Decide",
    body: "The forecast becomes a ranked list of things to do, each carrying the evidence behind it: days of cover, lead time, the signals that moved it.",
  },
  {
    num: "04",
    name: "Act",
    body: "Approve a reorder, move a transfer, hold a markdown. Every decision is recorded with its inputs, so the plan can be audited months later.",
  },
];

/**
 * The plain-English answer to "what is this" — the thing the page previously
 * never said outright. Four steps, because a planning platform that cannot be
 * explained in four steps will not be bought.
 */
export const WhatItDoes = () => (
  <section id="what-it-does" className="lc-section">
    <div className="lc-shell">
      <div className="lc-intro">
        <p className="lc-kicker">How it fits</p>
        <h2 className="lc-h2">From raw orders to an approved reorder</h2>
        <p className="lc-lede">
          One loop, running continuously against your own data. No migration
          project, no data-science team required to operate it.
        </p>
      </div>

      <ol className="lc-flow">
        {STEPS.map((s) => (
          <li key={s.num}>
            <span className="lc-flow-num">{s.num}</span>
            <h3 className="lc-flow-name">{s.name}</h3>
            <p className="lc-flow-body">{s.body}</p>
          </li>
        ))}
      </ol>
    </div>
  </section>
);
