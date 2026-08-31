const POINTS = [
  {
    title: "A model per SKU, not one model for everything",
    body: "Fast movers and long-tail lines do not behave alike, so they are not forecast alike. Each SKU is routed to the approach that fits its history, and the routing is visible rather than buried.",
  },
  {
    title: "New products forecast without history",
    body: "A zero-shot foundation model produces a usable curve for a SKU that has never been sold, which is exactly the case a purely statistical stack cannot serve.",
  },
  {
    title: "Accuracy is measured, not asserted",
    body: "Forecasts are backtested and scored per SKU against a naive baseline. Where the engine does not beat the baseline, it says so — that number is in the product, not just in a benchmark deck.",
  },
];

/**
 * The technical depth a planning buyer looks for, kept to what the ml/ package
 * actually implements. No accuracy percentages: we have not measured one on a
 * customer's data, so quoting one would be inventing proof.
 */
export const ForecastEngine = () => (
  <section id="engine" className="lc-section">
    <div className="lc-shell">
      <div className="lc-intro">
        <p className="lc-kicker">The engine</p>
        <h2 className="lc-h2">Per-SKU models, scored against what happened</h2>
        <p className="lc-lede">
          Forecasting is the part of this product that has to be right. Here is
          how it works, and how you can check it.
        </p>
      </div>

      <div className="lc-point-grid">
        {POINTS.map((p) => (
          <article key={p.title}>
            <h3 className="lc-h3">{p.title}</h3>
            <p className="lc-body">{p.body}</p>
          </article>
        ))}
      </div>
    </div>
  </section>
);
