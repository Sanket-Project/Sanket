const cases = [
  {
    metric: "−38%",
    label: "Markdown Write-offs",
    vertical: "Fashion & Apparel",
    title: "Apparel Group Stock Distribution",
    desc: "By forecasting localized demand quantiles, SANKET prevented end-of-season overstocking and optimized transfer logistics across 12 distribution warehouses.",
  },
  {
    metric: "Zero",
    label: "Surging Stockouts",
    vertical: "Consumer Electronics",
    title: "Holiday Surge Management",
    desc: "Integrated Google Trends and Reddit scraper caught consumer interest spikes 9 days before sales reflected, allowing pre-emptive factory restocking.",
  },
  {
    metric: "14 Days",
    label: "Lead-Time Reduction",
    vertical: "Pharmaceuticals",
    title: "GxP Compliant Auditing",
    desc: "Automated batch release quarantine workflows and immutable ledger audits accelerated regulatory handshakes and distribution clearance.",
  },
];

export default function LandingCaseStudies() {
  return (
    <section id="case-studies" className="py-24 sm:py-28 px-6 sm:px-10 relative border-t border-white/[0.05]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-14 text-center max-w-2xl mx-auto">
          <div className="flex items-center justify-center gap-3 mb-5">
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
            <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/60 uppercase">Outcomes</span>
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
          </div>
          <h2 className="text-4xl sm:text-5xl font-light tracking-tight"
            style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
            What good looks like.
          </h2>
          <p className="text-sm text-white/70 leading-relaxed mt-5 max-w-md mx-auto">
            Illustrative scenarios showing how SANKET helps scaling operators and
            compliance-driven networks take uncertainty out of the supply chain.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
          {cases.map((c, i) => (
            <div key={i} className="border border-white/[0.07] bg-[#0A0A0A] rounded-2xl p-7 flex flex-col justify-between h-full transition-all duration-300 hover:border-[#DEDBC8]/25 hover:shadow-[0_15px_40px_rgba(0,0,0,0.5)]">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#DEDBC8]/60">
                    {c.vertical}
                  </span>
                  <span className="font-mono text-[9px] tracking-[0.15em] uppercase text-white/40 border border-white/[0.1] rounded-full px-2 py-0.5">
                    Illustrative
                  </span>
                </div>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-5xl font-light tracking-tight text-[#E8E5D0]" style={{ fontFamily: "'DM Serif Display', serif" }}>
                    {c.metric}
                  </span>
                </div>
                <div className="font-mono text-[10px] uppercase text-white/60 tracking-[0.2em] mb-6">
                  {c.label}
                </div>
                <h3 className="text-lg font-medium text-white/90 mb-3 tracking-tight" style={{ fontFamily: "'DM Serif Display', serif" }}>
                  {c.title}
                </h3>
                <p className="text-xs sm:text-sm text-white/70 leading-relaxed">
                  {c.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
