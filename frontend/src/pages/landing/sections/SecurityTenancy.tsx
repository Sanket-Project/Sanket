const POINTS = [
  {
    title: "Isolation enforced by the database",
    body: "Every tenant's rows are separated by PostgreSQL row-level security, not by a WHERE clause someone has to remember. A query that forgets the tenant returns nothing rather than someone else's data.",
  },
  {
    title: "Decisions carry an audit trail",
    body: "Recommendations, overrides and approvals are recorded with the inputs that produced them, so a plan can be reconstructed months after it was agreed.",
  },
  {
    title: "GxP audit level for pharmaceutical workspaces",
    body: "A pharma workspace runs at GxP audit level with batch and shelf-life tracking, aligned to 21 CFR Part 11 expectations for electronic records.",
  },
];

/**
 * Kept deliberately precise. "Architected for" SOC 2 and HIPAA workflows is
 * true; "certified" would not be, and this page does not make claims it cannot
 * support.
 */
export const SecurityTenancy = () => (
  <section id="security" className="lc-section lc-section-alt">
    <div className="lc-shell">
      <div className="lc-intro">
        <p className="lc-kicker">Security</p>
        <h2 className="lc-h2">Your data stays yours</h2>
        <p className="lc-lede">
          Tenant isolation is an architectural property here, not a policy
          document. It is enforced at the database tier and tested as such.
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

      <p className="lc-note">
        Architected for SOC 2, HIPAA and 21 CFR Part 11 workflows.
      </p>
    </div>
  </section>
);
