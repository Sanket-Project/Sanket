const POINTS = [
  {
    title: "Forecasts from your first eight weeks of sales",
    body: "Until a model is trained on your data, each SKU is forecast by a pretrained foundation model (Chronos) applied to that SKU's own sales history. It needs at least eight weeks of it; a SKU with less is listed as not forecast, with the reason.",
  },
  {
    title: "New products are not guessed",
    body: "A SKU that has never sold gets no forecast curve: there is no history to extend, and another product's demand is not quietly substituted. It is shown as not forecast until it has sales.",
  },
  {
    title: "Accuracy is measured, not asserted",
    body: "Each forecast week is scored against what actually sold that week, using only forecasts made before the week began; historical backtests are labelled separately. Where a simple baseline does better, the evaluation says so.",
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
