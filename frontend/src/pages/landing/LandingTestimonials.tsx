import { useRef } from "react";
import { motion, useInView } from "framer-motion";

const TESTIMONIALS = [
  {
    quote:
      "We used to rebuild the demand plan in spreadsheets every Monday. Now the forecast is waiting for us, and we spend the time deciding what to do about it instead of arguing over the numbers.",
    role: "VP of Supply Chain",
    segment: "Mid-market apparel retailer",
  },
  {
    quote:
      "The shortage alerts caught two stockouts before they happened during our holiday peak. That alone paid for the platform several times over.",
    role: "Director of Planning",
    segment: "Consumer electronics brand",
  },
  {
    quote:
      "Onboarding connected our store and ERP the same afternoon. By the next morning we had forecasts for every SKU — no data team required.",
    role: "Head of Operations",
    segment: "Multi-vertical distributor",
  },
];

export default function LandingTestimonials() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <section id="testimonials" className="py-24 sm:py-28 px-6 sm:px-10 border-t border-white/[0.05]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-14 text-center max-w-2xl mx-auto">
          <div className="flex items-center justify-center gap-3 mb-5">
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
            <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/70 uppercase">In their words</span>
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
          </div>
          <h2 className="text-4xl sm:text-5xl font-light tracking-tight"
            style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
            Built for the people <span className="italic opacity-60">who plan.</span>
          </h2>
        </div>

        <div ref={ref} className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
          {TESTIMONIALS.map((t, i) => (
            <motion.figure
              key={i}
              initial={{ opacity: 0, y: 24 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: i * 0.12 }}
              className="border border-white/[0.07] bg-[#0A0A0A] rounded-2xl p-7 flex flex-col justify-between h-full"
            >
              <blockquote className="text-base text-white/80 leading-relaxed mb-6">
                "{t.quote}"
              </blockquote>
              <figcaption className="flex items-center justify-between pt-5 border-t border-white/[0.06]">
                <div>
                  <div className="text-sm font-medium text-[#E8E5D0]">{t.role}</div>
                  <div className="font-mono text-[11px] tracking-wide text-white/70">{t.segment}</div>
                </div>
                <span className="font-mono text-[9px] tracking-[0.15em] uppercase text-white/40 border border-white/[0.1] rounded-full px-2 py-0.5 shrink-0">
                  Illustrative
                </span>
              </figcaption>
            </motion.figure>
          ))}
        </div>
      </div>
    </section>
  );
}
