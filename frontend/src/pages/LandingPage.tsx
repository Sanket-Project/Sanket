import React, { useEffect, useRef, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  motion,
  AnimatePresence,
  useScroll,
  useInView,
  useTransform,
  useMotionValue,
  useSpring,
} from "framer-motion";
import axios from "axios";
import toast from "react-hot-toast";
import {
  X,
  ArrowRight,
  ArrowUpRight,
  Check,
  RefreshCw,
  Shirt,
  Cpu,
  Pill,
  Sprout,
  Wrench,
  Database,
  Zap,
  Bell,
  AlertCircle,
  Menu,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { useIndustryStore } from "@/stores/industry";
import { LogoMark } from "@/components/ui/Logo";
import type { IndustryCode } from "@/types/api";

type Ind = Exclude<IndustryCode, never>;

const inputCls =
  "w-full rounded-none border-0 border-b border-white/15 bg-transparent px-0 py-2.5 text-sm text-white placeholder-white/25 outline-none transition focus:border-[#DEDBC8]/60 focus:ring-0";

/** Tracks the user's `prefers-reduced-motion` setting (live). When true we skip
 * the particle canvas, the intro loader, and autoplaying video. */
const usePrefersReducedMotion = (): boolean => {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
};

const INDUSTRIES: { key: Ind; Icon: React.ComponentType<any>; name: string }[] = [
  { key: "fashion", Icon: Shirt, name: "Fashion & Apparel" },
  { key: "electronics", Icon: Cpu, name: "Consumer Electronics" },
  { key: "pharma", Icon: Pill, name: "Pharmaceuticals" },
  { key: "agrocenter", Icon: Sprout, name: "Agrocenter & Farm Inputs" },
  { key: "hardware", Icon: Wrench, name: "Tools & Hardware" },
];

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 1 · Cinematic Intro Loader
// ─────────────────────────────────────────────────────────────────────────────
const IntroLoader = ({ onDone }: { onDone: () => void }) => {
  useEffect(() => {
    // Marketing page: keep the intro under a second so content isn't gated.
    const t = setTimeout(onDone, 900);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <motion.div
      onClick={onDone}
      role="button"
      tabIndex={0}
      aria-label="Skip intro"
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black cursor-pointer"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.76, 0, 0.24, 1] }}
    >
      {/* Horizontal wipe curtains */}
      <motion.div
        className="absolute inset-0 bg-black origin-left"
        initial={{ scaleX: 1 }}
        animate={{ scaleX: 0 }}
        transition={{ duration: 0.7, ease: [0.76, 0, 0.24, 1], delay: 1.4 }}
      />
      {/* Logo */}
      <div className="relative flex flex-col items-center gap-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.8, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
          <LogoMark
            size={56}
            variant="bare"
            curveColor="#E8E5D0"
            className="mb-1"
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20, letterSpacing: "0.6em" }}
          animate={{ opacity: 1, y: 0, letterSpacing: "0.35em" }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          style={{ fontFamily: "'DM Serif Display', serif" }}
          className="text-5xl sm:text-7xl font-light text-[#E8E5D0]"
        >
          SANKET
        </motion.div>
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.55 }}
          className="h-px w-24 bg-[#DEDBC8]/30 origin-left"
        />
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.9 }}
          className="font-mono text-[9px] tracking-[0.4em] text-[#DEDBC8]/30 uppercase"
        >
          Predictive Intelligence
        </motion.p>
      </div>
    </motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 3 · Scroll Progress Bar
// ─────────────────────────────────────────────────────────────────────────────
const ScrollProgress = () => {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 });
  return (
    <motion.div
      style={{ scaleX, transformOrigin: "left" }}
      className="fixed top-0 left-0 right-0 h-[1.5px] z-[150] bg-gradient-to-r from-[#DEDBC8]/60 via-[#DEDBC8] to-[#DEDBC8]/60"
    />
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 4 · Count-Up Component
// ─────────────────────────────────────────────────────────────────────────────
const CountUp = ({ to, suffix = "", prefix = "", decimals = 0, duration = 2.2 }: {
  to: number; suffix?: string; prefix?: string; decimals?: number; duration?: number;
}) => {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const [val, setVal] = useState(0);

  useEffect(() => {
    if (!inView) return;
    let start: number | null = null;
    const step = (ts: number) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / (duration * 1000), 1);
      const eased = 1 - Math.pow(1 - progress, 4);
      setVal(eased * to);
      if (progress < 1) requestAnimationFrame(step);
      else setVal(to);
    };
    requestAnimationFrame(step);
  }, [inView, to, duration]);

  return (
    <span ref={ref}>
      {prefix}{val.toFixed(decimals)}{suffix}
    </span>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 5 · Trust Marquee
// ─────────────────────────────────────────────────────────────────────────────
const TRUST_BRANDS = [
  "SHOPIFY PLUS", "SAP ARIBA", "SALESFORCE", "ORACLE NETSUITE",
  "SNOWFLAKE", "DATABRICKS", "AWS", "MICROSOFT AZURE",
  "GOOGLE CLOUD", "RAZORPAY", "TWILIO", "TABLEAU",
];

const TrustMarquee = () => (
  <div className="trust-marquee relative py-10 border-y border-white/[0.05] overflow-hidden select-none">
    <p className="text-center font-mono text-[11px] tracking-[0.3em] text-white/70 uppercase mb-8">
      Integrates with your stack
    </p>
    <div className="absolute left-0 top-0 bottom-0 w-24 z-10 bg-gradient-to-r from-[#060606] to-transparent pointer-events-none" />
    <div className="absolute right-0 top-0 bottom-0 w-24 z-10 bg-gradient-to-l from-[#060606] to-transparent pointer-events-none" />
    <div className="marquee-row flex items-center" style={{ animation: "marquee 30s linear infinite" }}>
      {[...TRUST_BRANDS, ...TRUST_BRANDS].map((brand, i) => (
        <div key={i} className="flex items-center gap-8 mx-8 shrink-0">
          <span className="font-mono text-[11px] tracking-[0.3em] text-white/35 uppercase whitespace-nowrap hover:text-[#DEDBC8]/80 transition-colors duration-300">{brand}</span>
          <span className="w-1 h-1 rounded-full bg-white/[0.12] shrink-0" />
        </div>
      ))}
    </div>
    <div className="marquee-row flex items-center mt-0" style={{ animation: "marquee 30s linear infinite reverse", animationDelay: "-15s", marginTop: "-2.5rem" }}>
      {[...TRUST_BRANDS, ...TRUST_BRANDS].map((brand, i) => (
        <div key={i} className="flex items-center gap-8 mx-8 shrink-0 opacity-50">
          <span className="font-mono text-[11px] tracking-[0.3em] text-white/45 uppercase whitespace-nowrap">{brand}</span>
          <span className="w-1 h-1 rounded-full bg-white/[0.08] shrink-0" />
        </div>
      ))}
    </div>
  </div>
);

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 6 · How It Works
// ─────────────────────────────────────────────────────────────────────────────
const HOW_STEPS = [
  {
    num: "01",
    icon: Database,
    title: "Connect",
    sub: "Ingest",
    desc: "Connect your stores, ERP, POS, and warehouses in minutes — a secure, one-time setup with no engineering project and no disruption to your existing systems.",
    tags: ["Shopify", "SAP", "NetSuite", "WooCommerce"],
  },
  {
    num: "02",
    icon: Zap,
    title: "Forecast",
    sub: "Predict",
    desc: "Get a demand forecast for every SKU — with best-case, likely, and worst-case ranges so you can plan with confidence. Your full catalog refreshes in minutes, not days.",
    tags: ["Every SKU", "Best / likely / worst case", "Market signals"],
  },
  {
    num: "03",
    icon: Bell,
    title: "Act",
    sub: "Respond",
    desc: "Get an alert the moment a SKU is about to run short — with a ready-to-approve reorder and a markdown plan delivered straight into your workflow.",
    tags: ["Shortage alerts", "Reorder proposals", "Markdown plans"],
  },
];

const HowItWorks = ({ onCta }: { onCta: () => void }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <section id="how-it-works" className="py-24 sm:py-28 px-6 sm:px-10">
      <div className="max-w-6xl mx-auto">
        <div className="mb-14">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
            <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/60 uppercase">The Process</span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-light tracking-tight"
            style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
            From raw data to<br />
            <span className="italic opacity-60">decisive action</span> — in minutes.
          </h2>
        </div>

        <div ref={ref} className="relative grid grid-cols-1 md:grid-cols-3 gap-1.5">
          {/* Connector lines (desktop) */}
          <div className="hidden md:flex absolute top-20 left-[calc(33.33%-2rem)] right-[calc(33.33%-2rem)] h-px items-center">
            <motion.div
              className="flex-1 h-px bg-gradient-to-r from-[#DEDBC8]/20 to-[#DEDBC8]/20"
              initial={{ scaleX: 0 }}
              animate={inView ? { scaleX: 1 } : {}}
              transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1], delay: 0.4 }}
              style={{ transformOrigin: "left" }}
            />
          </div>

          {HOW_STEPS.map((step, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 30 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: i * 0.18 }}
              className="relative group"
            >
              <div className="border border-white/[0.06] rounded-xl p-7 sm:p-8 h-full bg-[#0A0A0A] hover:border-[#DEDBC8]/25 hover:shadow-[0_15px_40px_rgba(0,0,0,0.5)] transition-all duration-500 relative overflow-hidden">
                {/* glow */}
                <div className="absolute -top-16 -right-16 w-32 h-32 rounded-full bg-[#DEDBC8]/[0.03] blur-2xl group-hover:bg-[#DEDBC8]/[0.08] transition-all duration-700" />

                {/* Icon + number */}
                <div className="flex items-start justify-between mb-8">
                  <div className="w-10 h-10 rounded-lg border border-white/[0.08] flex items-center justify-center transition-all duration-500 group-hover:border-[#DEDBC8]/40 group-hover:scale-110 group-hover:-rotate-3">
                    <step.icon className="w-4 h-4 text-[#DEDBC8]/60 transition-colors duration-500 group-hover:text-[#DEDBC8]" />
                  </div>
                  <span className="font-mono text-xs tracking-[0.25em] text-[#DEDBC8]/40 transition-colors duration-500 group-hover:text-[#DEDBC8]/70">{step.num}</span>
                </div>

                {/* Text */}
                <div className="mb-1">
                  <span className="font-mono text-xs tracking-[0.3em] text-[#DEDBC8]/55 uppercase">{step.sub}</span>
                </div>
                <h3 className="text-2xl font-light mb-4" style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
                  {step.title}
                </h3>
                <p className="text-sm text-white/70 leading-relaxed mb-6">{step.desc}</p>

                {/* Tags */}
                <div className="flex flex-wrap gap-2">
                  {step.tags.map((tag, j) => (
                    <span key={j} className="font-mono text-[10px] tracking-wider text-[#DEDBC8]/50 border border-white/[0.08] rounded-full px-3 py-1 bg-white/[0.02]">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Mini CTA */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.7, delay: 0.7 }}
          className="mt-12 flex justify-center"
        >
          <button onClick={onCta}
            className="group flex items-center gap-2 font-mono text-xs tracking-[0.25em] uppercase text-white/60 hover:text-[#DEDBC8] transition-colors duration-300">
            Try the Sandbox <ArrowRight className="w-3 h-3 transition-transform duration-300 group-hover:translate-x-1" />
          </button>
        </motion.div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 7 · Testimonials
// NOTE: These quotes are placeholders attributed to role + segment only (no real
// names or company logos) and are tagged "Illustrative". Replace with real,
// attributed customer quotes — with permission — before a public launch.
// ─────────────────────────────────────────────────────────────────────────────
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

const Testimonials = () => {
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
              className="border border-white/[0.07] bg-[#0A0A0A] rounded-2xl p-7 flex flex-col justify-between h-full transition-all duration-500 hover:border-[#DEDBC8]/25 hover:-translate-y-1 hover:shadow-[0_15px_40px_rgba(0,0,0,0.5)]"
            >
              <blockquote className="text-base text-white/80 leading-relaxed mb-6">
                “{t.quote}”
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
};

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 8 · Final CTA
// ─────────────────────────────────────────────────────────────────────────────
const FinalCTA = ({ onBook, onSandbox }: { onBook: () => void; onSandbox: () => void }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <section ref={ref} className="relative py-24 sm:py-32 px-6 sm:px-10 overflow-hidden">
      {/* Radial glow */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <motion.div
          initial={{ opacity: 0, scale: 0.7 }}
          animate={inView ? { opacity: 1, scale: 1 } : {}}
          transition={{ duration: 1.6, ease: [0.16, 1, 0.3, 1] }}
          className="w-[600px] h-[600px] rounded-full"
          style={{
            background: "radial-gradient(circle, rgba(222,219,200,0.055) 0%, transparent 70%)",
          }}
        />
      </div>
      {/* Grid lines */}
      <div className="absolute inset-0 grid-bg opacity-40 pointer-events-none" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_transparent_30%,_#060606_75%)] pointer-events-none" />

      <div className="max-w-4xl mx-auto text-center relative z-10">
        <motion.div
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="flex items-center justify-center gap-3 mb-8"
        >
          <div className="flex-1 max-w-[80px] h-px bg-gradient-to-r from-transparent to-[#DEDBC8]/20" />
          <span className="font-mono text-xs tracking-[0.4em] text-[#DEDBC8]/55 uppercase">Start Now</span>
          <div className="flex-1 max-w-[80px] h-px bg-gradient-to-l from-transparent to-[#DEDBC8]/20" />
        </motion.div>

        <motion.h2
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          className="text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-light tracking-tight leading-[0.9] mb-8"
          style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}
        >
          Your supply chain<br />
          <span className="italic opacity-50">deserves certainty.</span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.4 }}
          className="text-base font-light text-white/65 max-w-md mx-auto mb-12 leading-relaxed"
        >
          Join forward-thinking enterprises using SANKET to eliminate guesswork and move at the speed of intelligence.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.55 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-3"
        >
          <button onClick={onBook}
            className="group px-8 py-4 bg-[#DEDBC8] hover:bg-[#E8E5D0] text-black text-xs font-medium tracking-widest uppercase rounded-full transition-all duration-300 flex items-center gap-2 hover:-translate-y-0.5 active:scale-[0.97] hover:shadow-[0_12px_40px_-10px_rgba(222,219,200,0.5)]">
            Book a Demo <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
          </button>
          <button onClick={onSandbox}
            className="group px-8 py-4 border border-white/[0.15] hover:border-[#DEDBC8]/40 text-white/70 hover:text-[#DEDBC8] text-xs font-medium tracking-widest uppercase rounded-full transition-all duration-300 flex items-center gap-2 bg-black/10 backdrop-blur-sm hover:-translate-y-0.5 active:scale-[0.97]">
            Try the Sandbox <ArrowUpRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </button>
        </motion.div>

        {/* Micro trust line */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ duration: 0.6, delay: 0.75 }}
          className="mt-8 font-mono text-xs tracking-[0.25em] text-white/45 uppercase"
        >
          No credit card · Cancel anytime · Set up in minutes
        </motion.p>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// LIVE TICKER
// ─────────────────────────────────────────────────────────────────────────────
const LiveTicker = () => {
  const actions = [
    "Synced 1,420 new sales — inventory positions updated across all locations.",
    "Refreshed demand forecasts for 8,200 SKUs ahead of next week's planning.",
    "Shortage alert: SKU-8820 is down to 4 days of cover — reorder ready to approve.",
  ];
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((p) => (p + 1) % actions.length), 4500);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 flex items-center gap-4 border-t border-white/[0.06] bg-black/50 backdrop-blur-xl px-6 md:px-10 py-3">
      <div className="flex items-center gap-2 shrink-0">
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
        </span>
        <span className="font-mono text-xs tracking-[0.2em] text-[#DEDBC8]/80 uppercase">Live activity</span>
      </div>
      <div className="w-px h-3 bg-white/10 shrink-0" />
      <div className="flex-1 overflow-hidden relative h-3.5">
        <AnimatePresence mode="wait">
          <motion.span
            key={idx}
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -10, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="absolute left-0 font-mono text-xs text-white/75 tracking-wide truncate w-full"
          >
            {actions[idx]}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// PULL UP WORDS
// ─────────────────────────────────────────────────────────────────────────────
const PullUp = ({
  text, className = "", delay = 0, showAsterisk = false, color = "#E8E5D0",
}: { text: string; className?: string; delay?: number; showAsterisk?: boolean; color?: string }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const words = text.split(" ");
  return (
    <span ref={ref} className={`inline-flex flex-wrap ${className}`}>
      {words.map((word, i) => {
        const isLast = i === words.length - 1;
        return (
          <span key={i} className="overflow-hidden inline-block mr-[0.22em] last:mr-0">
            <motion.span
              className="inline-block relative"
              style={{ color }}
              initial={{ y: "110%", opacity: 0 }}
              animate={inView ? { y: "0%", opacity: 1 } : {}}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: delay + i * 0.07 }}
            >
              {word}
              {isLast && showAsterisk && (
                <sup className="absolute top-[0.7em] -right-[0.25em] text-[0.28em] font-light opacity-60">*</sup>
              )}
            </motion.span>
          </span>
        );
      })}
    </span>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ANIM WORD
// ─────────────────────────────────────────────────────────────────────────────
const AnimWord = ({ word, progress, range }: { word: string; progress: any; range: [number, number] }) => {
  const opacity = useTransform(progress, range, [0.15, 1]);
  return <motion.span style={{ opacity }} className="inline-block mr-[0.22em] last:mr-0">{word}</motion.span>;
};

// ─────────────────────────────────────────────────────────────────────────────
// FLOATING PARTICLES (Hero Canvas)
// ─────────────────────────────────────────────────────────────────────────────
const FloatingParticles = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    const particles: Array<{
      x: number;
      y: number;
      size: number;
      speedX: number;
      speedY: number;
      opacity: number;
    }> = [];

    const resize = () => {
      canvas.width = canvas.parentElement?.clientWidth || window.innerWidth;
      canvas.height = canvas.parentElement?.clientHeight || window.innerHeight;
    };

    resize();
    window.addEventListener("resize", resize);

    const particleCount = 25;
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 1.5 + 0.5,
        speedX: (Math.random() - 0.5) * 0.12,
        speedY: (Math.random() - 0.5) * 0.12 - 0.08,
        opacity: Math.random() * 0.4 + 0.1,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(222, 219, 200, ${p.opacity})`;
        ctx.fill();

        p.x += p.speedX;
        p.y += p.speedY;

        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
      });

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none w-full h-full z-0 opacity-50" />;
};

// ─────────────────────────────────────────────────────────────────────────────
// FADE CARD
// ─────────────────────────────────────────────────────────────────────────────
const FadeCard = ({ children, index }: { children: React.ReactNode; index: number }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.div ref={ref}
      initial={{ opacity: 0, y: 24 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1], delay: index * 0.12 }}
    >{children}</motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// FEATURE CARD
// ─────────────────────────────────────────────────────────────────────────────
const FeatureCard = ({ icon, num, title, items, onClick }: {
  icon: string; num: string; title: string; items: string[]; onClick?: () => void;
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.5);
  const rotateX = useSpring(useTransform(my, [0, 1], [8, -8]), { stiffness: 220, damping: 22 });
  const rotateY = useSpring(useTransform(mx, [0, 1], [-8, 8]), { stiffness: 220, damping: 22 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    mx.set(x / width);
    my.set(y / height);
  };

  const handleMouseLeave = () => {
    mx.set(0.5);
    my.set(0.5);
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ perspective: 1000 }}
      className="h-full"
    >
      <motion.div
        style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
        className="group relative bg-[#0C0C0C] border border-white/[0.06] rounded-xl overflow-hidden flex flex-col justify-between h-full transition-all duration-300 hover:border-[#DEDBC8]/25 hover:shadow-[0_20px_50px_rgba(0,0,0,0.6)]"
      >
        <div className="absolute inset-0 pointer-events-none opacity-[0.025]"
          style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,1) 2px, rgba(255,255,255,1) 3px)" }} />
        <div className="absolute -top-20 -left-20 w-40 h-40 rounded-full bg-[#DEDBC8]/[0.04] blur-3xl group-hover:bg-[#DEDBC8]/[0.09] transition-all duration-700 pointer-events-none" />
        <div className="relative p-7 sm:p-8" style={{ transform: "translateZ(30px)" }}>
          <div className="flex items-start justify-between mb-8">
            <img src={icon} alt={title} className="w-9 h-9 rounded object-cover opacity-90 border border-white/[0.08]" />
            <span className="font-mono text-xs text-white/40 tracking-[0.2em]">{num}</span>
          </div>
          <h3 className="text-base sm:text-lg font-semibold mb-5 tracking-tight group-hover:text-[#DEDBC8] transition-colors duration-300" style={{ color: "#E8E5D0" }}>{title}</h3>
          <ul className="flex flex-col gap-3">
            {items.map((item, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="mt-[3px] w-3.5 h-3.5 shrink-0 border border-[#DEDBC8]/30 rounded-sm flex items-center justify-center">
                  <Check className="w-2 h-2 text-[#DEDBC8]/60" />
                </span>
                <span className="text-xs sm:text-sm text-white/60 leading-relaxed tracking-wide">{item}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="relative px-7 sm:px-8 pb-6" style={{ transform: "translateZ(20px)" }}>
          <div className="w-full h-px bg-white/[0.05] mb-5" />
          <button onClick={onClick} className="group/cta flex items-center gap-1.5 text-xs font-mono tracking-wider text-white/60 hover:text-[#DEDBC8] transition-colors duration-300 uppercase">
            <span>Try the Sandbox</span>
            <ArrowUpRight className="w-3 h-3 transition-transform duration-300 group-hover/cta:translate-x-0.5 group-hover/cta:-translate-y-0.5" />
          </button>
        </div>
      </motion.div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ARCHITECTURE CARD
// ─────────────────────────────────────────────────────────────────────────────
const ArchCard = ({ title, desc, num, tag }: { title: string; desc: string; num: string; tag: string }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  return (
    <motion.div ref={ref}
      initial={{ opacity: 0, y: 30 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      className="group relative border-t border-white/[0.08] hover:border-[#DEDBC8]/25 pt-8 pb-6 pr-6 transition-colors duration-500"
    >
      <motion.div
        initial={{ scaleY: 0 }}
        animate={inView ? { scaleY: 1 } : {}}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
        className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-[#DEDBC8]/40 via-[#DEDBC8]/15 to-transparent origin-top group-hover:from-[#DEDBC8] group-hover:via-[#DEDBC8]/40 transition-all duration-500"
      />
      <div className="pl-6 group-hover:translate-x-1.5 transition-transform duration-500">
        <div className="flex items-center gap-3 mb-5">
          <span className="font-mono text-xs tracking-[0.25em] text-white/35 uppercase">{num}</span>
          <div className="flex-1 h-px bg-white/[0.05]" />
          <span className="font-mono text-xs tracking-[0.2em] text-[#DEDBC8]/55 uppercase">{tag}</span>
        </div>
        <h3 className="text-xl sm:text-2xl font-light tracking-tight mb-4 group-hover:text-[#DEDBC8] transition-colors duration-500"
          style={{ color: "#E8E5D0", fontFamily: "'DM Serif Display', serif" }}>{title}</h3>
        <p className="text-sm text-white/70 leading-relaxed tracking-wide">{desc}</p>
      </div>
    </motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// PLATFORM TOUR
// ─────────────────────────────────────────────────────────────────────────────
type TourTab = "forecasting" | "trends" | "inventory";

const PlatformTour = ({ onBook }: { onBook: () => void }) => {
  const [activeTab, setActiveTab] = useState<TourTab>("forecasting");
  const [reorderLoading, setReorderLoading] = useState(false);
  const [reorderApproved, setReorderApproved] = useState(false);

  const handleApproveReorder = () => {
    setReorderLoading(true);
    setTimeout(() => {
      setReorderLoading(false);
      setReorderApproved(true);
      toast.success("Purchase order PO-2026-8820 transmitted to SAP NetSuite!");
    }, 1200);
  };

  const tabs: { id: TourTab; label: string; desc: string }[] = [
    {
      id: "forecasting",
      label: "Demand Forecasting",
      desc: "See a clear demand forecast for every SKU, with best-case, likely, and worst-case ranges — so you can plan inventory for the scenario you choose instead of guessing.",
    },
    {
      id: "trends",
      label: "Real-Time Market Signals",
      desc: "SANKET watches search interest, social trends, and economic indicators for you, and adjusts the forecast automatically when demand starts to shift — before it shows up in sales.",
    },
    {
      id: "inventory",
      label: "Inventory Control Tower",
      desc: "Act the moment something needs attention. Turn alerts into ready-to-approve reorders and restock in a single click, synced straight back to your ERP.",
    },
  ];

  return (
    <section id="platform-tour" className="py-24 sm:py-28 px-6 sm:px-10 relative bg-[#070707]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-14">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
            <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/60 uppercase">Platform Tour</span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-light tracking-tight"
            style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
            Step inside the <span className="italic opacity-60">SANKET Engine.</span>
          </h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Tab Selector & Descriptions (Left Column) */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id !== "inventory") setReorderApproved(false);
                }}
                className={`text-left p-6 rounded-xl border transition-all duration-300 relative overflow-hidden ${
                  activeTab === tab.id
                    ? "border-[#DEDBC8]/30 bg-white/[0.02]"
                    : "border-white/[0.05] bg-transparent hover:border-white/[0.12] hover:bg-white/[0.01]"
                }`}
              >
                {activeTab === tab.id && (
                  <motion.div
                    layoutId="activeTabGlow"
                    className="absolute inset-0 bg-[#DEDBC8]/[0.01] pointer-events-none"
                    initial={false}
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                <div className="flex items-center gap-3 mb-2">
                  <span className={`font-mono text-xs ${activeTab === tab.id ? "text-[#DEDBC8]" : "text-white/35"}`}>
                    {tab.id === "forecasting" ? "01" : tab.id === "trends" ? "02" : "03"}
                  </span>
                  <h3 className={`text-base font-medium tracking-tight ${activeTab === tab.id ? "text-[#E8E5D0]" : "text-white/60"}`}>
                    {tab.label}
                  </h3>
                </div>
                {activeTab === tab.id && (
                  <motion.p
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className="text-xs text-white/65 leading-relaxed pl-6"
                  >
                    {tab.desc}
                  </motion.p>
                )}
              </button>
            ))}
            <button onClick={onBook} className="group mt-4 px-6 py-3.5 bg-[#DEDBC8] hover:bg-[#E8E5D0] text-black text-xs font-semibold tracking-widest uppercase rounded-full transition-all duration-300 flex items-center justify-center gap-2 self-start hover:-translate-y-0.5 active:scale-[0.97] hover:shadow-[0_10px_30px_-10px_rgba(222,219,200,0.45)]">
              Book a Demo <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
            </button>
          </div>

          {/* Interactive Screen Display (Right Column) */}
          <div className="lg:col-span-7 border border-white/[0.08] rounded-xl bg-[#090909] p-6 min-h-[380px] flex flex-col justify-between shadow-2xl relative overflow-hidden">
            {/* Screen Header mock */}
            <div className="flex items-center justify-between pb-4 border-b border-white/[0.06] mb-6 select-none">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-white/10" />
                <span className="w-2.5 h-2.5 rounded-full bg-white/10" />
                <span className="w-2.5 h-2.5 rounded-full bg-white/10" />
                <span className="font-mono text-[10px] text-white/35 tracking-wider ml-4">
                  {activeTab === "forecasting" ? "CORE // FORECAST_RUNNER" : activeTab === "trends" ? "FEEDS // SENTIMENT_SCRAPE" : "ALERTS // CONTROL_TOWER"}
                </span>
              </div>
              <span className="font-mono text-[9px] text-[#DEDBC8]/60 border border-[#DEDBC8]/20 rounded px-2 py-0.5 uppercase">
                Illustrative demo
              </span>
            </div>

            <div className="flex-1 flex flex-col justify-center">
              <AnimatePresence mode="wait">
                {activeTab === "forecasting" && (
                  <motion.div
                    key="forecasting"
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.3 }}
                    className="w-full h-full flex flex-col gap-6"
                  >
                    {/* SVG Chart mock */}
                    <div className="relative h-44 border border-white/[0.06] bg-[#050505] rounded-xl p-2 overflow-hidden flex items-end shadow-inner select-none">
                      {/* Subtle Background Grid Lines */}
                      <svg className="absolute inset-0 w-full h-full z-0" viewBox="0 0 100 100" preserveAspectRatio="none">
                        {/* Horizontal Gridlines */}
                        <line x1="0" y1="20" x2="100" y2="20" stroke="rgba(255, 255, 255, 0.025)" strokeWidth="0.5" />
                        <line x1="0" y1="40" x2="100" y2="40" stroke="rgba(255, 255, 255, 0.025)" strokeWidth="0.5" />
                        <line x1="0" y1="60" x2="100" y2="60" stroke="rgba(255, 255, 255, 0.025)" strokeWidth="0.5" />
                        <line x1="0" y1="80" x2="100" y2="80" stroke="rgba(255, 255, 255, 0.025)" strokeWidth="0.5" />
                        
                        {/* Vertical Gridlines */}
                        <line x1="20" y1="0" x2="20" y2="100" stroke="rgba(255, 255, 255, 0.02)" strokeWidth="0.5" />
                        <line x1="40" y1="0" x2="40" y2="100" stroke="rgba(255, 255, 255, 0.02)" strokeWidth="0.5" />
                        <line x1="60" y1="0" x2="60" y2="100" stroke="rgba(255, 255, 255, 0.02)" strokeWidth="0.5" />
                        <line x1="80" y1="0" x2="80" y2="100" stroke="rgba(255, 255, 255, 0.02)" strokeWidth="0.5" />
                      </svg>

                      <motion.svg
                        className="w-full h-full relative z-10"
                        viewBox="0 0 100 100"
                        preserveAspectRatio="none"
                        initial={{ clipPath: "inset(0 100% 0 0)" }}
                        animate={{ clipPath: "inset(0 0% 0 0)" }}
                        transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
                      >
                        <defs>
                          {/* Glow filter for forecast corridor and pulse markers */}
                          <filter id="corridorGlow" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="1.5" result="blur" />
                            <feMerge>
                              <feMergeNode in="blur" />
                              <feMergeNode in="SourceGraphic" />
                            </feMerge>
                          </filter>
                        </defs>

                        {/* Shaded p10-p90 Forecast corridor with gold glow */}
                        <path
                          d="M 40,72 L 50,55 L 60,40 L 70,30 L 80,32 L 90,20 L 90,65 L 80,72 L 70,68 L 60,78 L 50,85 L 40,72 Z"
                          fill="rgba(222, 219, 200, 0.05)"
                          stroke="rgba(222, 219, 200, 0.12)"
                          strokeWidth="0.5"
                          filter="url(#corridorGlow)"
                        />
                        
                        {/* Actual Sales Line (Historical) */}
                        <path
                          id="tourActualPath"
                          d="M 10,75 L 20,80 L 30,60 L 40,72"
                          fill="none"
                          stroke="rgba(255, 255, 255, 0.85)"
                          strokeWidth="1.5"
                        />
                        
                        {/* p50 Base Forecast Line with dash animation */}
                        <path
                          id="tourForecastPath"
                          d="M 40,72 L 50,68 L 60,56 L 70,48 L 80,50 L 90,38"
                          fill="none"
                          stroke="#DEDBC8"
                          strokeDasharray="2,3"
                          strokeWidth="1.8"
                          style={{ animation: "marchingDashes 1.2s linear infinite" }}
                        />

                        {/* Timeline Divider TODAY */}
                        <line x1="40" y1="5" x2="40" y2="95" stroke="rgba(222, 219, 200, 0.3)" strokeDasharray="2,2" strokeWidth="0.75" />

                        {/* Animated Tracing Dots */}
                        {/* Actual Sales Dot Tracer */}
                        <circle r="2" fill="#fff" filter="url(#corridorGlow)">
                          <animateMotion dur="3s" repeatCount="indefinite" path="M 10,75 L 20,80 L 30,60 L 40,72" />
                        </circle>
                        {/* Forecast p50 Dot Tracer */}
                        <circle r="2.2" fill="#DEDBC8" filter="url(#corridorGlow)">
                          <animateMotion dur="2.5s" repeatCount="indefinite" path="M 40,72 L 50,68 L 60,56 L 70,48 L 80,50 L 90,38" />
                        </circle>
                      </motion.svg>

                      {/* Timeline Divider Text Badge Overlay */}
                      <motion.div
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.7 }}
                        className="absolute top-[8%] left-[40%] -translate-x-1/2 bg-[#DEDBC8]/10 text-[#DEDBC8] font-mono text-[8px] tracking-wider px-1.5 py-0.5 rounded border border-[#DEDBC8]/25 backdrop-blur-sm select-none z-20"
                      >
                        TODAY
                      </motion.div>

                      {/* Interactive Chart Tooltip Badges */}
                      <motion.div
                        initial={{ opacity: 0, y: 6, scale: 0.92 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.9 }}
                        className="absolute bottom-[24%] left-[16%] -translate-x-1/2 bg-[#0A0A0A]/90 border border-white/[0.05] rounded px-2 py-0.5 pointer-events-none select-none z-20 shadow-lg"
                      >
                        <span className="font-mono text-[8px] text-white/35 block uppercase leading-none">actual</span>
                        <span className="text-[9px] text-white/80 font-mono font-medium">$12,420</span>
                      </motion.div>

                      <motion.div
                        initial={{ opacity: 0, y: 6, scale: 0.92 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 1.25 }}
                        className="absolute top-[28%] left-[68%] -translate-x-1/2 bg-[#0A0A0A]/95 border border-[#DEDBC8]/30 rounded px-2.5 py-1 pointer-events-none select-none z-20 shadow-[0_10px_25px_rgba(0,0,0,0.8)]"
                      >
                        <span className="font-mono text-[8px] text-[#DEDBC8]/60 block uppercase leading-none">p50 forecast</span>
                        <span className="text-[9px] text-[#DEDBC8] font-mono font-medium">$16,200</span>
                      </motion.div>

                      {/* Confidence Corridor Labels */}
                      <motion.div
                        initial={{ opacity: 0, x: 8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 1.4 }}
                        className="absolute top-[12%] right-[4%] bg-[#0A0A0A]/80 border border-white/[0.05] rounded px-1.5 py-0.5 text-right z-20 select-none"
                      >
                        <span className="font-mono text-[8px] text-white/30 block uppercase leading-none">quantile</span>
                        <span className="text-[8px] text-white/60 font-mono">p90 (Bull)</span>
                      </motion.div>
                      <motion.div
                        initial={{ opacity: 0, x: 8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 1.5 }}
                        className="absolute bottom-[24%] right-[4%] bg-[#0A0A0A]/80 border border-white/[0.05] rounded px-1.5 py-0.5 text-right z-20 select-none"
                      >
                        <span className="font-mono text-[8px] text-white/30 block uppercase leading-none">quantile</span>
                        <span className="text-[8px] text-white/60 font-mono">p10 (Bear)</span>
                      </motion.div>

                      {/* Interactive Legend */}
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.35 }}
                        className="absolute top-2.5 left-2.5 flex gap-4 select-none z-20 bg-black/40 backdrop-blur-sm px-2 py-1 rounded-md border border-white/[0.03]">
                        <span className="flex items-center gap-1.5 font-mono text-[9px] text-white/70">
                          <span className="w-2.5 h-0.5 bg-white/80 inline-block" /> Actual Sales
                        </span>
                        <span className="flex items-center gap-1.5 font-mono text-[9px] text-[#DEDBC8]">
                          <span className="w-2.5 h-0.5 border-t border-dashed border-[#DEDBC8] inline-block" /> SANKET Forecast
                        </span>
                      </motion.div>
                    </div>
                    {/* Metrics Footer */}
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { label: "accuracy*", value: "94.2%" },
                        { label: "forecast refresh", value: "< 5 min" },
                        { label: "planning horizon", value: "26 weeks" },
                      ].map((m, i) => (
                        <motion.div
                          key={m.label}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.45 + i * 0.12 }}
                          className="border border-white/[0.04] rounded p-2.5 bg-white/[0.005]"
                        >
                          <div className="font-mono text-[9px] text-white/45 uppercase mb-1">{m.label}</div>
                          <div className="font-semibold text-sm text-[#DEDBC8]">{m.value}</div>
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {activeTab === "trends" && (
                  <motion.div
                    key="trends"
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.3 }}
                    className="w-full h-full flex flex-col gap-4"
                  >
                    <div className="font-mono text-[10px] text-white/70 mb-1">LIVE MARKET SIGNALS (REAL-TIME):</div>
                    <div className="flex flex-col gap-2.5">
                      {[
                        { word: "Linen Shirts", source: "Google Trends / Reddit", volume: "+180%", status: "Positive", color: "text-emerald-400" },
                        { word: "Overnight Repair Serum", source: "TikTok / Instagram", volume: "+340%", status: "Strong Positive", color: "text-emerald-400 font-medium" },
                        { word: "Anodized Case Cover", source: "Google Shopping", volume: "-12%", status: "Neutral", color: "text-white/70" },
                        { word: "Agro Feed Formula-3", source: "Economic & weather data", volume: "+72%", status: "Positive", color: "text-emerald-400" },
                      ].map((t, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -14 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1], delay: 0.1 + idx * 0.09 }}
                          className="flex items-center justify-between border border-white/[0.05] rounded-lg p-3 bg-white/[0.005] hover:border-white/10 hover:bg-white/[0.015] transition-colors">
                          <div>
                            <div className="text-xs font-semibold text-white/85 flex items-center gap-2">
                              {t.word}
                              <span className="font-mono text-[9px] font-light text-white/30">via {t.source}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-4 text-right">
                            <div>
                              <div className="font-mono text-[9px] text-white/30 uppercase">volume</div>
                              <div className="text-[10px] font-semibold font-mono text-[#DEDBC8]">{t.volume}</div>
                            </div>
                            <div className="min-w-[80px]">
                              <div className="font-mono text-[9px] text-white/30 uppercase">sentiment</div>
                              <div className={`text-[10px] font-mono ${t.color}`}>{t.status}</div>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {activeTab === "inventory" && (
                  <motion.div
                    key="inventory"
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.3 }}
                    className="w-full h-full flex flex-col gap-5"
                  >
                    <div className="font-mono text-[10px] text-white/40 mb-1">CRITICAL COVERAGE ALERTS:</div>
                    <motion.div
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
                      className="border border-[#DEDBC8]/15 rounded-lg p-4 bg-[#DEDBC8]/[0.01] flex flex-col gap-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <AlertCircle size={14} className="text-amber-400 animate-pulse" />
                          <span className="font-mono text-xs text-white/80 font-semibold">SKU-8820</span>
                          <span className="text-[10px] text-white/40 font-mono">(Fashion & Apparel)</span>
                        </div>
                        <span className="font-mono text-[9px] px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                          Shortage Risk (4 Days Remaining)
                        </span>
                      </div>

                      <div className="text-xs text-white/60 leading-relaxed border-t border-white/[0.04] pt-3">
                        SANKET recommends restocking now to avoid an estimated $142k in lost sales from this shortage.
                      </div>

                      <div className="flex items-center justify-between mt-2 pt-3 border-t border-white/[0.04]">
                        <div className="flex items-center gap-6">
                          <div>
                            <div className="font-mono text-[9px] text-white/30 uppercase">reorder qty</div>
                            <div className="text-[10px] font-semibold text-white/70">1,200 units</div>
                          </div>
                          <div>
                            <div className="font-mono text-[9px] text-white/30 uppercase">lead time</div>
                            <div className="text-[10px] font-semibold text-white/70">7 days</div>
                          </div>
                        </div>
                        <button
                          onClick={handleApproveReorder}
                          disabled={reorderLoading || reorderApproved}
                          className={`px-4 py-2 font-mono text-[9px] uppercase tracking-widest rounded-md border transition-all duration-300 flex items-center gap-2 ${
                            reorderApproved
                              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                              : "bg-[#DEDBC8] border-transparent text-black hover:bg-[#E8E5D0]"
                          }`}
                        >
                          {reorderLoading ? (
                            <>
                              <RefreshCw size={10} className="animate-spin" /> Sending to ERP...
                            </>
                          ) : reorderApproved ? (
                            <>✓ Approved</>
                          ) : (
                            <>Approve Auto-Reorder</>
                          )}
                        </button>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// KNOWLEDGE GRAPH VISUALIZATION
// ─────────────────────────────────────────────────────────────────────────────
const KnowledgeGraph = () => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <div ref={ref} className="w-full max-w-[460px] aspect-square rounded-2xl border border-white/[0.08] bg-[#080808] p-6 relative overflow-hidden flex flex-col justify-between shadow-2xl select-none">
      {/* Background glowing auroras */}
      <div className="absolute -top-12 -left-12 w-36 h-36 rounded-full bg-[#DEDBC8]/[0.03] blur-3xl pointer-events-none" />
      <div className="absolute -bottom-12 -right-12 w-36 h-36 rounded-full bg-indigo-500/[0.03] blur-3xl pointer-events-none" />
      <div className="absolute inset-0 grid-bg opacity-[0.15] pointer-events-none" />

      {/* Header telemetry info */}
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.05] relative z-10">
        <span className="font-mono text-[9px] text-[#DEDBC8]/60 uppercase tracking-widest flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Core Data Flow
        </span>
        <span className="font-mono text-[8px] text-white/30">ID // SANKET_EKG_V2</span>
      </div>

      {/* SVG Canvas for lines and flows */}
      <div className="flex-1 relative my-4 min-h-[240px]">
        <svg className="w-full h-full absolute inset-0 z-0" viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs>
            <filter id="glow-heavy" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            
            <linearGradient id="lineGradLeft" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="rgba(255, 255, 255, 0.15)" />
              <stop offset="100%" stopColor="#DEDBC8" stopOpacity="0.8" />
            </linearGradient>
            <linearGradient id="lineGradRight" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#DEDBC8" stopOpacity="0.8" />
              <stop offset="100%" stopColor="rgba(222, 219, 200, 0.15)" />
            </linearGradient>
          </defs>

          {/* Core static connection paths — draw in on scroll */}
          {/* Left inputs to center */}
          {([
            "M 20,25 Q 35,25 50,50",
            "M 15,50 Q 32.5,50 50,50",
            "M 20,75 Q 35,75 50,50",
          ] as const).map((d, i) => (
            <motion.path
              key={d}
              d={d}
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="1"
              initial={{ pathLength: 0 }}
              animate={inView ? { pathLength: 1 } : {}}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.2 + i * 0.12 }}
            />
          ))}

          {/* Center to right outputs */}
          {([
            "M 50,50 Q 65,25 80,25",
            "M 50,50 Q 65,50 85,50",
            "M 50,50 Q 65,75 80,75",
          ] as const).map((d, i) => (
            <motion.path
              key={d}
              d={d}
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="1"
              initial={{ pathLength: 0 }}
              animate={inView ? { pathLength: 1 } : {}}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.65 + i * 0.12 }}
            />
          ))}

          {/* Animated data pulse lines (marching dashes) — fade in after the lines draw */}
          <motion.g initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ duration: 0.8, delay: 1.1 }}>
            {/* Left inputs */}
            <path d="M 20,25 Q 35,25 50,50" fill="none" stroke="url(#lineGradLeft)" strokeWidth="1.2" strokeDasharray="6, 18" strokeDashoffset="0" className="animate-dash" style={{ animation: "marchingDashes 2.5s linear infinite" }} />
            <path d="M 15,50 Q 32.5,50 50,50" fill="none" stroke="url(#lineGradLeft)" strokeWidth="1.2" strokeDasharray="6, 18" strokeDashoffset="0" className="animate-dash" style={{ animation: "marchingDashes 2s linear infinite" }} />
            <path d="M 20,75 Q 35,75 50,50" fill="none" stroke="url(#lineGradLeft)" strokeWidth="1.2" strokeDasharray="6, 18" strokeDashoffset="0" className="animate-dash" style={{ animation: "marchingDashes 3s linear infinite" }} />

            {/* Right outputs */}
            <path d="M 50,50 Q 65,25 80,25" fill="none" stroke="url(#lineGradRight)" strokeWidth="1.2" strokeDasharray="6, 18" strokeDashoffset="0" className="animate-dash" style={{ animation: "marchingDashes 2.2s linear infinite reverse" }} />
            <path d="M 50,50 Q 65,50 85,50" fill="none" stroke="url(#lineGradRight)" strokeWidth="1.2" strokeDasharray="6, 18" strokeDashoffset="0" className="animate-dash" style={{ animation: "marchingDashes 1.8s linear infinite reverse" }} />
            <path d="M 50,50 Q 65,75 80,75" fill="none" stroke="url(#lineGradRight)" strokeWidth="1.2" strokeDasharray="6, 18" strokeDashoffset="0" className="animate-dash" style={{ animation: "marchingDashes 2.6s linear infinite reverse" }} />
          </motion.g>

          {/* Glowing central node */}
          <motion.g initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ duration: 0.7, delay: 0.55 }}>
            <circle cx="50" cy="50" r="8" fill="rgba(222, 219, 200, 0.15)" stroke="#DEDBC8" strokeWidth="1" filter="url(#glow-heavy)" className="animate-pulse" />
            <circle cx="50" cy="50" r="3" fill="#DEDBC8" />
          </motion.g>

          {/* Left node circles */}
          {([
            { cx: 20, cy: 25 },
            { cx: 15, cy: 50 },
            { cx: 20, cy: 75 },
          ] as const).map((n, i) => (
            <motion.circle
              key={`l-${i}`}
              cx={n.cx}
              cy={n.cy}
              fill="#fff"
              initial={{ r: 0, opacity: 0 }}
              animate={inView ? { r: 2, opacity: 0.8 } : {}}
              transition={{ duration: 0.5, ease: [0.34, 1.56, 0.64, 1], delay: 0.15 + i * 0.12 }}
            />
          ))}

          {/* Right node circles */}
          {([
            { cx: 80, cy: 25 },
            { cx: 85, cy: 50 },
            { cx: 80, cy: 75 },
          ] as const).map((n, i) => (
            <motion.circle
              key={`r-${i}`}
              cx={n.cx}
              cy={n.cy}
              fill="#DEDBC8"
              initial={{ r: 0, opacity: 0 }}
              animate={inView ? { r: 2, opacity: 1 } : {}}
              transition={{ duration: 0.5, ease: [0.34, 1.56, 0.64, 1], delay: 1.15 + i * 0.12 }}
            />
          ))}
        </svg>

        {/* CSS animation style injected locally */}
        <style>{`
          @keyframes marchingDashes {
            from { stroke-dashoffset: 24; }
            to { stroke-dashoffset: 0; }
          }
        `}</style>

        {/* Labels Overlay - Styled HTML for absolute clarity */}
        {/* Left Inputs */}
        {([
          { top: "top-[18%]", left: "left-[2%]", tag: "Source // ERP", name: "Shopify / SAP" },
          { top: "top-[50%]", left: "left-[0%]", tag: "Feed // Macro", name: "FRED Indicator" },
          { top: "top-[82%]", left: "left-[2%]", tag: "Feed // Social", name: "Trends Scraper" },
        ] as const).map((l, i) => (
          <motion.div
            key={l.tag}
            initial={{ opacity: 0, x: -10 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.2 + i * 0.12 }}
            className={`absolute ${l.top} ${l.left} -translate-y-1/2 flex flex-col items-start bg-[#0A0A0A]/90 border border-white/[0.06] backdrop-blur-sm px-2.5 py-1 rounded`}
          >
            <span className="font-mono text-[8px] text-white/35 uppercase tracking-wider">{l.tag}</span>
            <span className="text-[10px] text-white/70 font-medium">{l.name}</span>
          </motion.div>
        ))}

        {/* Central Pipeline */}
        <motion.div
          initial={{ opacity: 0, scale: 0.85 }}
          animate={inView ? { opacity: 1, scale: 1 } : {}}
          transition={{ duration: 0.55, ease: [0.34, 1.56, 0.64, 1], delay: 0.6 }}
          className="absolute top-[34%] left-[50%] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center bg-black/90 border border-[#DEDBC8]/30 backdrop-blur-md px-3 py-1.5 rounded-lg shadow-lg select-none"
        >
          <span className="font-mono text-[8px] text-[#DEDBC8] uppercase tracking-[0.2em] font-semibold">vector db</span>
          <span className="text-[10px] text-white/95 font-mono">pgvector</span>
        </motion.div>

        {/* Right Outputs */}
        {([
          { top: "top-[18%]", right: "right-[2%]", tag: "forecast core", name: "Chronos AI" },
          { top: "top-[50%]", right: "right-[0%]", tag: "correlation", name: "Trend Scorer" },
          { top: "top-[82%]", right: "right-[2%]", tag: "trigger engine", name: "Shortage Alerts" },
        ] as const).map((l, i) => (
          <motion.div
            key={l.tag}
            initial={{ opacity: 0, x: 10 }}
            animate={inView ? { opacity: 1, x: 0 } : {}}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 1.1 + i * 0.12 }}
            className={`absolute ${l.top} ${l.right} -translate-y-1/2 flex flex-col items-end bg-[#0A0A0A]/90 border border-white/[0.06] backdrop-blur-sm px-2.5 py-1 rounded text-right`}
          >
            <span className="font-mono text-[8px] text-[#DEDBC8]/50 uppercase tracking-wider">{l.tag}</span>
            <span className="text-[10px] text-[#DEDBC8] font-medium">{l.name}</span>
          </motion.div>
        ))}
      </div>

      {/* Telemetry Summary Footer */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 1.35 }}
        className="relative z-10 bg-black/50 border border-white/[0.05] backdrop-blur-md rounded-xl p-3 flex items-center justify-between">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[8px] tracking-[0.3em] text-[#DEDBC8]/70 uppercase">active ingestion telemetry</span>
          <span className="text-[10px] text-white/65 leading-relaxed font-mono">
            Pipeline: <span className="text-emerald-400">Online</span> · Ingesting 1,420 rows/sec
          </span>
        </div>
        <span className="font-mono text-[9px] text-[#DEDBC8] bg-[#DEDBC8]/5 px-2.5 py-1 rounded border border-[#DEDBC8]/10">
          768-D Vector Projection
        </span>
      </motion.div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// CASE STUDIES / SUCCESS STORIES
// ─────────────────────────────────────────────────────────────────────────────
const CaseStudies = () => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
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

        <div ref={ref} className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
          {cases.map((c, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 28 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: i * 0.14 }}
              className="border border-white/[0.07] bg-[#0A0A0A] rounded-2xl p-7 flex flex-col justify-between h-full transition-all duration-300 hover:border-[#DEDBC8]/25 hover:-translate-y-1 hover:shadow-[0_15px_40px_rgba(0,0,0,0.5)]"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-[#DEDBC8]/60">
                    {c.vertical}
                  </span>
                  <span className="font-mono text-[9px] tracking-[0.15em] uppercase text-white/40 border border-white/[0.1] rounded-full px-2 py-0.5">
                    Illustrative
                  </span>
                </div>
                <div className="flex items-baseline gap-2 mb-2 overflow-hidden">
                  <motion.span
                    initial={{ y: "110%", opacity: 0 }}
                    animate={inView ? { y: "0%", opacity: 1 } : {}}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.25 + i * 0.14 }}
                    className="inline-block text-5xl font-light tracking-tight text-[#E8E5D0]"
                    style={{ fontFamily: "'DM Serif Display', serif" }}
                  >
                    {c.metric}
                  </motion.span>
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
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// PRICING
// ─────────────────────────────────────────────────────────────────────────────
type PricingTier = {
  tier: string;
  monthly: number | "Custom";
  annual: number | "Custom";
  trialLabel?: string;
  desc: string;
  featured: boolean;
  cta: string;
  feats: string[];
};

const PRICING_TIERS: PricingTier[] = [
  {
    tier: "Starter",
    monthly: 0,
    annual: 0,
    trialLabel: "14-day trial",
    desc: "For small teams piloting demand forecasting on a single vertical.",
    featured: false,
    cta: "Try the Sandbox",
    feats: [
      "1 industry workspace",
      "Up to 500 active SKUs",
      "Forecasts for every SKU",
      "Weekly shortage alerts",
      "Community support",
    ],
  },
  {
    tier: "Growth",
    monthly: 499,
    annual: 4990,
    desc: "For scaling operators who need real-time signals and automation.",
    featured: true,
    cta: "Book a Demo",
    feats: [
      "Up to 3 industry workspaces",
      "Unlimited SKUs",
      "Best / likely / worst-case forecasts",
      "Real-time trend & market signals",
      "Reorder + markdown automation",
      "Priority email & chat support",
    ],
  },
  {
    tier: "Scale",
    monthly: 1399,
    annual: 13999,
    desc: "For mid-market enterprises that need scale and multi-vertical analytics.",
    featured: false,
    cta: "Book a Demo",
    feats: [
      "Up to 10 industry workspaces",
      "Up to 100,000 active SKUs",
      "Custom models per vertical",
      "Daily trend & sentiment tracking",
      "Dedicated database replica option",
      "Priority 24/7 support",
    ],
  },
  {
    tier: "Enterprise",
    monthly: "Custom",
    annual: "Custom",
    desc: "For regulated, multi-region enterprises with compliance demands.",
    featured: false,
    cta: "Book a Demo",
    feats: [
      "Unlimited workspaces & seats",
      "GxP 21 CFR Part 11 audit trails",
      "Multi-region tenant routing",
      "SSO / SAML + data isolation",
      "Dedicated solutions engineer",
      "Custom uptime SLA",
    ],
  },
];

const Pricing = ({ onBook, onSandbox }: { onBook: () => void; onSandbox: () => void }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  const [billing, setBilling] = useState<"monthly" | "annual">("monthly");

  const [currency, setCurrency] = useState<"USD" | "INR" | "EUR">(() => {
    try {
      const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (
        timeZone.includes("Calcutta") ||
        timeZone.includes("Kolkata") ||
        timeZone.includes("Asia/Kolkata") ||
        timeZone.includes("Asia/Calcutta")
      ) {
        return "INR";
      }
      if (timeZone.includes("Europe")) {
        return "EUR";
      }
    } catch (e) {
      console.error("Timezone detection failed, using fallback:", e);
    }
    return "USD";
  });

  const [exchangeRates, setExchangeRates] = useState<Record<string, number>>({
    USD: 1.0,
    INR: 83.5,
    EUR: 0.92,
  });

  useEffect(() => {
    // Fetch live exchange rates
    axios
      .get("https://open.er-api.com/v6/latest/USD")
      .then((res) => {
        if (res.data && res.data.rates) {
          setExchangeRates({
            USD: 1.0,
            INR: res.data.rates.INR || 83.5,
            EUR: res.data.rates.EUR || 0.92,
          });
        }
      })
      .catch((err) => {
        console.error("Failed to fetch live exchange rates, using fallbacks:", err);
      });

    // Geolocation to refine currency based on region
    axios
      .get("https://ipapi.co/json/")
      .then((res) => {
        if (res.data && res.data.country_code) {
          const country = res.data.country_code;
          if (country === "IN") {
            setCurrency("INR");
          } else if (
            [
              "AT", "BE", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT",
              "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES", "EU"
            ].includes(country)
          ) {
            setCurrency("EUR");
          } else if (country === "US") {
            setCurrency("USD");
          }
        }
      })
      .catch((err) => {
        console.error("Geolocation check failed, sticking to timezone initial:", err);
      });
  }, []);

  const formatPrice = (priceVal: number | string) => {
    if (typeof priceVal === "string") return priceVal;
    if (priceVal === 0) {
      if (currency === "INR") return "₹0";
      if (currency === "EUR") return "€0";
      return "$0";
    }

    const rate = exchangeRates[currency] || 1.0;
    const converted = priceVal * rate;

    try {
      const formatter = new Intl.NumberFormat(
        currency === "INR" ? "en-IN" : currency === "EUR" ? "de-DE" : "en-US",
        {
          style: "currency",
          currency: currency,
          maximumFractionDigits: 0,
          minimumFractionDigits: 0,
        }
      );
      return formatter.format(converted);
    } catch {
      const symbol = currency === "INR" ? "₹" : currency === "EUR" ? "€" : "$";
      return `${symbol}${Math.round(converted).toLocaleString()}`;
    }
  };

  return (
    <section id="pricing" className="py-24 sm:py-28 px-6 sm:px-10 relative">
      <div className="max-w-6xl mx-auto">
        <div className="mb-14 text-center max-w-2xl mx-auto">
          <div className="flex items-center justify-center gap-3 mb-5">
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
            <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/60 uppercase">Plans & Pricing</span>
            <div className="w-4 h-px bg-[#DEDBC8]/30" />
          </div>
          <h2 className="text-4xl sm:text-5xl font-light tracking-tight"
            style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
            Pricing that scales <span className="italic opacity-60">with you.</span>
          </h2>
          <p className="text-sm text-white/65 leading-relaxed mt-5 max-w-md mx-auto">
            Start free, upgrade when you are ready. No credit card required for the sandbox.
          </p>

          {/* Billing period + currency selectors */}
          <div className="flex flex-col items-center gap-4 mt-8">
            <div className="inline-flex items-center bg-white/[0.03] backdrop-blur-md border border-white/[0.08] rounded-full p-1 select-none">
              {(["monthly", "annual"] as const).map((period) => (
                <button
                  key={period}
                  onClick={() => setBilling(period)}
                  className={`px-5 py-1.5 rounded-full text-xs font-mono tracking-wider capitalize transition-all duration-300 flex items-center gap-2 ${
                    billing === period
                      ? "bg-[#DEDBC8] text-black shadow-lg font-medium"
                      : "text-white/55 hover:text-white/85"
                  }`}
                >
                  {period}
                  {period === "annual" && (
                    <span className={`text-[9px] tracking-wide rounded-full px-1.5 py-0.5 ${billing === "annual" ? "bg-black/15" : "bg-[#DEDBC8]/15 text-[#DEDBC8]"}`}>
                      2 months free
                    </span>
                  )}
                </button>
              ))}
            </div>
            <div className="inline-flex bg-white/[0.03] backdrop-blur-md border border-white/[0.08] rounded-full p-1 select-none">
              {(["USD", "INR", "EUR"] as const).map((curr) => (
                <button
                  key={curr}
                  onClick={() => setCurrency(curr)}
                  className={`px-4 py-1.5 rounded-full text-xs font-mono tracking-wider transition-all duration-300 ${
                    currency === curr
                      ? "bg-[#DEDBC8] text-black shadow-lg font-medium"
                      : "text-white/55 hover:text-white/85"
                  }`}
                >
                  {curr} ({curr === "INR" ? "₹" : curr === "EUR" ? "€" : "$"})
                </button>
              ))}
            </div>
          </div>
        </div>

        <div ref={ref} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 items-stretch">
          {PRICING_TIERS.map((p, i) => (
            <motion.div
              key={p.tier}
              initial={{ opacity: 0, y: 28 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: i * 0.12 }}
              className={`relative rounded-2xl p-8 flex flex-col h-full backdrop-blur-sm transition-all duration-500 hover:-translate-y-1.5 ${
                p.featured
                  ? "border border-[#DEDBC8]/40 bg-[#DEDBC8]/[0.04] shadow-[0_30px_70px_-30px_rgba(222,219,200,0.35)] hover:shadow-[0_40px_80px_-30px_rgba(222,219,200,0.45)]"
                  : "border border-white/[0.07] bg-white/[0.015] hover:border-[#DEDBC8]/20 hover:shadow-[0_20px_50px_-20px_rgba(0,0,0,0.7)]"
              }`}
            >
              {p.featured && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 font-mono text-[10px] tracking-[0.2em] uppercase px-4 py-1 rounded-full bg-[#DEDBC8] text-black whitespace-nowrap">
                  Most Popular
                </span>
              )}
              <span className="font-mono text-xs tracking-[0.25em] uppercase text-[#DEDBC8]/75">{p.tier}</span>
              {(() => {
                // Free trial and Custom tiers ignore the billing toggle. Paid
                // tiers always show an effective monthly price so they compare
                // like-for-like; annual shows the discounted /mo + "billed annually".
                const isCustom = p.monthly === "Custom";
                const isFree = p.monthly === 0;
                const effectiveMonthly =
                  billing === "annual"
                    ? Math.round((p.annual as number) / 12)
                    : (p.monthly as number);
                const priceText = isCustom
                  ? "Custom"
                  : isFree
                  ? formatPrice(0)
                  : formatPrice(effectiveMonthly);
                const periodLabel = isCustom
                  ? "annual"
                  : isFree
                  ? p.trialLabel
                  : "mo";
                return (
                  <>
                    <div className="flex items-baseline gap-2 mt-4">
                      <span className="text-3xl sm:text-4xl md:text-5xl font-light tracking-tight" style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
                        {priceText}
                      </span>
                      <span className="font-mono text-xs text-white/50">/ {periodLabel}</span>
                    </div>
                    <div className="font-mono text-[11px] tracking-wide text-white/45 mt-1.5 h-4">
                      {!isCustom && !isFree && billing === "annual"
                        ? `${formatPrice(p.annual as number)} billed annually`
                        : ""}
                    </div>
                  </>
                );
              })()}
              <p className="text-sm text-white/70 leading-relaxed mt-4 mb-7">{p.desc}</p>

              <ul className="flex flex-col gap-3 mb-8">
                {p.feats.map((f) => (
                  <li key={f} className="flex items-start gap-3">
                    <span className="mt-[2px] w-4 h-4 shrink-0 border border-[#DEDBC8]/30 rounded-sm flex items-center justify-center">
                      <Check className="w-2.5 h-2.5 text-[#DEDBC8]/70" />
                    </span>
                    <span className="text-[13px] text-white/65 leading-relaxed">{f}</span>
                  </li>
                ))}
              </ul>

              <button
                onClick={p.featured ? onBook : p.tier === "Starter" ? onSandbox : onBook}
                className={`mt-auto w-full rounded-full py-3 text-xs font-medium tracking-widest uppercase transition-all duration-300 active:scale-[0.98] ${
                  p.featured
                    ? "bg-[#DEDBC8] text-black hover:bg-[#E8E5D0]"
                    : "border border-white/[0.12] text-white/60 hover:border-[#DEDBC8]/40 hover:text-[#DEDBC8]"
                }`}
              >
                {p.cta}
              </button>
            </motion.div>
          ))}
        </div>

        <p className="text-center font-mono text-xs tracking-[0.2em] text-white/45 uppercase mt-12">
          Enterprise-grade security · Cancel anytime
        </p>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
export const LandingPage = () => {
  const navigate = useNavigate();
  const loginSandbox = useAuthStore((s) => s.loginSandbox);
  const setIndustry = useIndustryStore((s) => s.setIndustry);

  const [modal, setModal] = useState<null | "book" | "sandbox">(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const [formSuccess, setFormSuccess] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [showLoader, setShowLoader] = useState(() => !sessionStorage.getItem("sanket_visited"));
  const [lead, setLead] = useState({
    name: "", email: "", company: "", industry: "fashion", tier: "growth", message: "",
  });

  const reducedMotion = usePrefersReducedMotion();

  const aboutRef = useRef(null);
  const { scrollYProgress: aboutProg } = useScroll({ target: aboutRef, offset: ["start 0.95", "start 0.35"] });

  // Hero parallax: the background video drifts down and zooms slightly as the
  // hero scrolls out, so foreground copy appears to float above it.
  const heroRef = useRef(null);
  const { scrollYProgress: heroProg } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const heroY = useTransform(heroProg, [0, 1], [0, 110]);
  const heroScale = useTransform(heroProg, [0, 1], [1, 1.15]);
  const heroContentOpacity = useTransform(heroProg, [0, 0.75], [1, 0.15]);

  const handleLoaderDone = useCallback(() => {
    sessionStorage.setItem("sanket_visited", "1");
    setShowLoader(false);
  }, []);

  // Respect reduced-motion: never gate content behind the intro animation.
  useEffect(() => {
    if (reducedMotion && showLoader) handleLoaderDone();
  }, [reducedMotion, showLoader, handleLoaderDone]);

  const aboutText = "Across five global verticals — Fashion, Electronics, Pharma, Hardware, and Agrocenter — SANKET brings your sales, inventory, and market signals into one place, forecasts demand for every product, and tells you exactly what to reorder and when. Your team plans with confidence instead of spreadsheets, and acts on what's about to happen rather than what already did.";
  const aboutWords = aboutText.split(" ");

  const submitDemo = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await axios.post("/api/v1/demo-requests", lead);
      setFormSuccess(true);
      toast.success("Demo request submitted!");
      setLead({ name: "", email: "", company: "", industry: "fashion", tier: "growth", message: "" });
    } catch { toast.error("Failed to submit. Please try again."); }
    finally { setFormLoading(false); }
  };

  const launchSandbox = async (code: Ind) => {
    setLaunching(true);
    try {
      // Auth runs server-side via /auth/sandbox-session — no demo credentials
      // are shipped in the client bundle.
      await loginSandbox();
      setIndustry(code);
      toast.success(`Sandbox launched!`);
      setModal(null);
      navigate("/workspace", { replace: true });
    } catch { toast.error("Could not launch sandbox."); }
    finally { setLaunching(false); }
  };

  const goToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMobileMenuOpen(false);
  };
  const sectionLinks = [
    { label: "Platform", id: "features" },
    { label: "How It Works", id: "how-it-works" },
    { label: "Architecture", id: "architecture" },
    { label: "Pricing", id: "pricing" },
  ];

  return (
    <div className="bg-[#060606] min-h-screen overflow-x-hidden relative" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Space+Grotesk:wght@300;400;500;600&display=swap');
        ::selection { background: rgba(222,219,200,0.12); color: #E8E5D0; }
        .grid-bg {
          background-image:
            linear-gradient(to right, rgba(222,219,200,0.025) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(222,219,200,0.025) 1px, transparent 1px);
          background-size: 80px 80px;
        }
        .glow-line { background: linear-gradient(90deg, transparent, rgba(222,219,200,0.3), transparent); }
        @keyframes marquee {
          from { transform: translateX(0); }
          to { transform: translateX(-50%); }
        }
        .trust-marquee:hover .marquee-row { animation-play-state: paused !important; }
        @keyframes auroraDrift {
          0%   { transform: translate3d(0, 0, 0) scale(1); }
          50%  { transform: translate3d(-2%, 1.5%, 0) scale(1.06); }
          100% { transform: translate3d(0, 0, 0) scale(1); }
        }
        .aurora-layer { animation: auroraDrift 26s ease-in-out infinite; }
        html { scroll-behavior: smooth; }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after {
            animation-duration: 0.001ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.001ms !important;
            scroll-behavior: auto !important;
          }
          .aurora-layer { animation: none !important; }
        }
        ::-webkit-scrollbar { width: 3px; background: #060606; }
        ::-webkit-scrollbar-thumb { background: rgba(222,219,200,0.12); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(222,219,200,0.25); }
      `}</style>

      {/* ── Ambient page background (aurora glows + masked grid) ── */}
      <div className="fixed inset-0 -z-10 pointer-events-none overflow-hidden">
        <div
          className="aurora-layer absolute inset-[-15%]"
          style={{
            background:
              "radial-gradient(38% 30% at 16% 6%, rgba(222,219,200,0.08) 0%, transparent 60%)," +
              "radial-gradient(44% 34% at 86% 18%, rgba(99,102,241,0.10) 0%, transparent 60%)," +
              "radial-gradient(42% 34% at 12% 46%, rgba(124,58,237,0.07) 0%, transparent 60%)," +
              "radial-gradient(48% 40% at 88% 64%, rgba(8,145,178,0.07) 0%, transparent 60%)," +
              "radial-gradient(46% 40% at 30% 90%, rgba(222,219,200,0.06) 0%, transparent 60%)",
          }}
        />
        <div
          className="grid-bg absolute inset-0 opacity-100"
          style={{
            maskImage: "linear-gradient(to bottom, transparent 0%, #000 6%, #000 94%, transparent 100%)",
            WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, #000 6%, #000 94%, transparent 100%)",
          }}
        />
      </div>

      {/* ── Loader ── */}
      <AnimatePresence>
        {showLoader && !reducedMotion && <IntroLoader onDone={handleLoaderDone} />}
      </AnimatePresence>

      {/* ── Scroll Progress ── */}
      <ScrollProgress />

      {/* ══════════════════════ NAV ══════════════════════ */}
      <header className="fixed top-0 left-0 right-0 z-50 flex flex-col items-center pt-5">
        <motion.nav
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: showLoader ? 1.0 : 0 }}
          className="flex items-center gap-1 bg-white/[0.04] backdrop-blur-2xl border border-white/[0.08] rounded-full px-2 py-2"
        >
          <span className="font-mono text-xs tracking-[0.3em] text-[#DEDBC8]/80 uppercase px-4">SANKET</span>
          <div className="w-px h-3 bg-white/10 mx-1" />

          {/* Desktop section links */}
          {sectionLinks.map((l) => (
            <button
              key={l.id}
              onClick={() => goToSection(l.id)}
              className="hidden md:inline-block px-4 py-1.5 rounded-full text-xs font-medium tracking-wide text-white/65 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
            >
              {l.label}
            </button>
          ))}

          {/* Sign in (desktop) */}
          <button
            onClick={() => navigate("/login")}
            className="hidden md:inline-block px-4 py-1.5 rounded-full text-xs font-medium tracking-wide text-white/65 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
          >
            Sign In
          </button>

          {/* Primary CTA */}
          <button
            onClick={() => setModal("book")}
            className="px-4 py-1.5 rounded-full text-xs font-medium tracking-wide bg-[#DEDBC8] text-black hover:bg-[#E8E5D0] ml-1 transition-all duration-200 active:scale-95 hover:shadow-[0_4px_20px_-4px_rgba(222,219,200,0.5)]"
          >
            Book a Demo
          </button>

          {/* Mobile menu toggle */}
          <button
            onClick={() => setMobileMenuOpen((o) => !o)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
            className="md:hidden w-8 h-8 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/[0.06] transition-all duration-200 ml-1"
          >
            {mobileMenuOpen ? <X size={16} /> : <Menu size={16} />}
          </button>
        </motion.nav>

        {/* Mobile dropdown menu */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="md:hidden mt-2 w-[min(92vw,320px)] flex flex-col bg-[#0A0A0A]/95 backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-2 shadow-2xl"
            >
              {sectionLinks.map((l) => (
                <button
                  key={l.id}
                  onClick={() => goToSection(l.id)}
                  className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
                >
                  {l.label}
                </button>
              ))}
              <button
                onClick={() => { setMobileMenuOpen(false); navigate("/login"); }}
                className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
              >
                Sign In
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); setModal("sandbox"); }}
                className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
              >
                Try the Sandbox
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); setModal("book"); }}
                className="mt-1 text-center px-4 py-3 rounded-xl text-sm font-semibold bg-[#DEDBC8] text-black hover:bg-[#E8E5D0] transition-all duration-200"
              >
                Book a Demo
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {/* ══════════════════════ HERO ══════════════════════ */}
      <section id="hero" ref={heroRef} className="relative h-screen p-3 md:p-5">
        <div className="relative h-full rounded-2xl md:rounded-3xl overflow-hidden flex flex-col justify-end">
          {reducedMotion ? (
            <img
              src={`${import.meta.env.BASE_URL}assets/predictive_model.png`}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
            />
          ) : (
            <>
              <motion.div style={{ y: heroY, scale: heroScale }} className="absolute inset-0">
                <video
                  src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4"
                  autoPlay loop muted playsInline
                  poster={`${import.meta.env.BASE_URL}assets/predictive_model.png`}
                  preload="metadata"
                  className="absolute inset-0 w-full h-full object-cover"
                />
              </motion.div>
              <FloatingParticles />
            </>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/25 to-black/45" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-transparent to-transparent" />
          <div className="noise-overlay opacity-[0.5] mix-blend-overlay pointer-events-none absolute inset-0" />

          <motion.div
            style={reducedMotion ? undefined : { opacity: heroContentOpacity }}
            className="relative z-10 p-6 sm:p-10 md:p-16 pb-20 sm:pb-24"
          >
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: showLoader ? 2.3 : 0.2 }}
              className="flex items-center gap-3 mb-8"
            >
              <div className="w-6 h-px bg-[#DEDBC8]/50" />
              <span className="font-mono text-xs tracking-[0.3em] text-[#DEDBC8]/70 uppercase">
                AI Demand Forecasting for Supply Chains
              </span>
            </motion.div>

            <div className="mb-10 max-w-4xl">
              <h1 className="font-light leading-[0.95] tracking-[-0.02em]"
                style={{
                  fontFamily: "'DM Serif Display', serif",
                  fontSize: "clamp(2.5rem, 7vw, 5.5rem)",
                  color: "#E8E5D0",
                }}>
                <PullUp text="Stop guessing demand." delay={showLoader ? 1.3 : 0.1} color="#E8E5D0"
                  className="text-[length:inherit] leading-[inherit] tracking-[inherit]" />
                <br />
                <span className="italic opacity-70">
                  <PullUp text="Forecast every SKU." delay={showLoader ? 1.45 : 0.25} color="#E8E5D0"
                    className="text-[length:inherit] leading-[inherit] tracking-[inherit]" />
                </span>
              </h1>
            </div>

            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-6 sm:gap-12">
              <motion.p
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: showLoader ? 1.7 : 0.6 }}
                className="max-w-md text-base font-light tracking-wide leading-relaxed"
                style={{ color: "rgba(232,229,208,0.9)" }}
              >
                SANKET turns your sales, inventory, and live market signals into one
                forecasting engine — so you order the right stock, cut markdowns,
                and never get caught short.
              </motion.p>

              <motion.button
                onClick={() => setModal("sandbox")}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: showLoader ? 1.85 : 0.75 }}
                className="group flex items-center gap-0 overflow-hidden border border-[#DEDBC8]/25 hover:border-[#DEDBC8]/60 transition-all duration-500 rounded-full bg-black/20 backdrop-blur-sm"
              >
                <span className="px-6 py-3 text-xs font-medium tracking-widest uppercase text-[#E8E5D0]/85 group-hover:text-[#E8E5D0] transition-colors duration-300">
                  Try the Sandbox
                </span>
                <div className="w-10 h-10 rounded-full border-l border-[#DEDBC8]/15 flex items-center justify-center group-hover:bg-[#DEDBC8]/15 transition-all duration-300">
                  <ArrowRight className="w-3.5 h-3.5 text-[#E8E5D0]/50 group-hover:text-[#E8E5D0] group-hover:translate-x-0.5 transition-all duration-300" />
                </div>
              </motion.button>
            </div>
          </motion.div>
          <LiveTicker />
        </div>
      </section>

      {/* ══════════════════════ TRUST MARQUEE ══════════════════════ */}
      <TrustMarquee />

      {/* ══════════════════════ ABOUT ══════════════════════ */}
      <section id="about" className="py-24 sm:py-28 px-6 sm:px-10">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-8 mb-14">
            <div>
              <div className="flex items-center gap-3 mb-5">
                <div className="w-4 h-px bg-[#DEDBC8]/30" />
                <span className="font-mono text-[9px] tracking-[0.35em] text-[#DEDBC8]/30 uppercase">About the Platform</span>
              </div>
              <h2 className="text-4xl sm:text-5xl md:text-6xl font-light leading-[1.05] tracking-tight"
                style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
                <PullUp text="We build" delay={0} color="#E8E5D0" className="text-[length:inherit] leading-[inherit]" />
                <br />
                <span className="italic opacity-60">
                  <PullUp text="intelligence," delay={0.1} color="#E8E5D0" className="text-[length:inherit] leading-[inherit]" />
                </span>
                <br />
                <PullUp text="for the" delay={0.2} color="#E8E5D0" className="text-[length:inherit] leading-[inherit]" />
                <br />
                <PullUp text="predictive enterprise." delay={0.3} color="#E8E5D0" className="text-[length:inherit] leading-[inherit]" />
              </h2>
            </div>
            <div className="max-w-xs">
              <p className="text-sm font-light leading-relaxed tracking-wide text-white/75">
                Five industries. One platform. Fewer stockouts, less markdown, and a plan you can trust.
              </p>
            </div>
          </div>

          <div className="w-full h-px glow-line mb-14 opacity-40" />

          <div ref={aboutRef} className="max-w-4xl mx-auto">
            <p className="text-2xl sm:text-3xl md:text-4xl font-light leading-relaxed tracking-tight select-none"
              style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
              {aboutWords.map((word, i) => {
                const p = i / aboutWords.length;
                return (
                  <React.Fragment key={i}>
                    <AnimWord word={word} progress={aboutProg} range={[Math.max(0, p - 0.08), Math.min(1, p + 0.08)]} />
                    {i < aboutWords.length - 1 && " "}
                  </React.Fragment>
                );
              })}
            </p>
          </div>

          {/* Count-up metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mt-16 pt-12 border-t border-white/[0.05]">
            {[
              { val: 94.2, suffix: "%", decimals: 1, label: "Forecast Accuracy" },
              { val: 38, prefix: "−", suffix: "%", decimals: 0, label: "Markdown Reduction" },
              { val: 5, suffix: "", decimals: 0, label: "Industry Verticals" },
              { val: 300, suffix: "+", decimals: 0, label: "Enterprise Integrations" },
            ].map((m, i) => (
              <FadeCard key={i} index={i}>
                <div>
                  <div className="font-mono text-3xl sm:text-4xl font-light tracking-tight mb-2" style={{ color: "#E8E5D0" }}>
                    <CountUp to={m.val} suffix={m.suffix} prefix={m.prefix ?? ""} decimals={m.decimals} />
                  </div>
                  <div className="font-mono text-xs tracking-[0.25em] text-white/60 uppercase">{m.label}</div>
                </div>
              </FadeCard>
            ))}
          </div>
          <p className="font-mono text-[11px] tracking-[0.15em] text-white/40 mt-6">
            Illustrative figures from pilot modeling — not a guarantee of results.
          </p>
        </div>
      </section>

      {/* ══════════════════════ FEATURES ══════════════════════ */}
      <section id="features" className="py-24 sm:py-28 px-6 sm:px-10">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-12">
            <div>
              <div className="flex items-center gap-3 mb-5">
                <div className="w-4 h-px bg-[#DEDBC8]/30" />
                <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/60 uppercase">Platform Modules</span>
              </div>
              <h2 className="text-3xl sm:text-4xl md:text-5xl font-light tracking-tight leading-tight"
                style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
                Enterprise-grade infrastructure<br />
                <span className="italic opacity-50">for vertical forecasting.</span>
              </h2>
            </div>
            <p className="max-w-xs text-sm font-light text-white/65 leading-relaxed tracking-wide">
              Built for pure precision. Powered by foundation AI and real-time market intelligence.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-1.5">
            <FadeCard index={0}>
              <div className="relative rounded-xl overflow-hidden min-h-[380px] lg:min-h-[520px] border border-white/[0.06] group hover:border-[#DEDBC8]/25 transition-colors duration-300">
                {reducedMotion ? (
                  <img
                    src={`${import.meta.env.BASE_URL}assets/data_pipeline.png`}
                    alt=""
                    className="absolute inset-0 w-full h-full object-cover"
                  />
                ) : (
                  <video
                    src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260406_133058_0504132a-0cf3-4450-a370-8ea3b05c95d4.mp4"
                    autoPlay loop muted playsInline
                    poster={`${import.meta.env.BASE_URL}assets/data_pipeline.png`}
                    preload="none"
                    className="absolute inset-0 w-full h-full object-cover transition-transform duration-[1600ms] ease-out group-hover:scale-[1.06]"
                  />
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/35 to-transparent" />
                <div className="absolute bottom-0 left-0 right-0 p-7">
                  <div className="font-mono text-xs tracking-[0.25em] text-white/65 uppercase mb-2">00</div>
                  <h3 className="text-base font-light tracking-tight" style={{ color: "#E8E5D0", fontFamily: "'DM Serif Display', serif" }}>
                    Your operational canvas.
                  </h3>
                </div>
              </div>
            </FadeCard>
            <FadeCard index={1}>
              <FeatureCard
                icon={`${import.meta.env.BASE_URL}assets/sanket_forecast_run.png`}
                num="01" title="Forecast every SKU."
                items={["A demand forecast for every product", "Best-case, likely, and worst-case ranges", "Plan for the scenario you choose", "Forecasts from day one — no history needed"]}
                onClick={() => setModal("sandbox")}
              />
            </FadeCard>
            <FadeCard index={2}>
              <FeatureCard
                icon={`${import.meta.env.BASE_URL}assets/sanket_trend_engine.png`}
                num="02" title="Catch demand shifts early."
                items={["Tracks search, social, and economic signals", "Spots trends before they hit your sales", "Adjusts the forecast automatically"]}
                onClick={() => setModal("sandbox")}
              />
            </FadeCard>
            <FadeCard index={3}>
              <FeatureCard
                icon={`${import.meta.env.BASE_URL}assets/sanket_secure_architecture.png`}
                num="03" title="Secure by design."
                items={["Your data stays isolated from every other tenant", "Audit trails built for regulated industries", "Architected for SOC 2, HIPAA & GxP workflows"]}
                onClick={() => setModal("sandbox")}
              />
            </FadeCard>
          </div>
        </div>
      </section>

      {/* ══════════════════════ PLATFORM TOUR ══════════════════════ */}
      <PlatformTour onBook={() => setModal("book")} />

      {/* ══════════════════════ HOW IT WORKS ══════════════════════ */}
      <HowItWorks onCta={() => setModal("sandbox")} />

      {/* ══════════════════════ ARCHITECTURE ══════════════════════ */}
      <section id="architecture" className="py-24 sm:py-28 px-6 sm:px-10 relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_transparent_30%,_rgba(6,6,6,0.55)_85%)] pointer-events-none" />
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="mb-14">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-4 h-px bg-[#DEDBC8]/30" />
              <span className="font-mono text-xs tracking-[0.35em] text-[#DEDBC8]/60 uppercase">System Design</span>
            </div>
            <h2 className="text-4xl sm:text-5xl md:text-6xl font-light tracking-tight"
              style={{ fontFamily: "'DM Serif Display', serif", color: "#E8E5D0" }}>
              <PullUp text="Designed for" delay={0} color="#E8E5D0" className="text-[length:inherit] leading-[inherit]" />
              <br />
              <span className="italic">
                <PullUp text="high-scale isolation." delay={0.15} color="#E8E5D0" className="text-[length:inherit] leading-[inherit]" />
              </span>
            </h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            {/* Left: System design cards */}
            <div className="lg:col-span-7 grid grid-cols-1 gap-0 border-l border-white/[0.06]">
              <ArchCard num="L-01" tag="Compute" title="Decoupled Compute"
                desc="Isolated async FastAPI Backend and ML Inference microservices optimize inference pipelines via dedicated ports 8000 and 8001, ensuring zero cross-tenant latency contamination." />
              <ArchCard num="L-02" tag="Data Layer" title="Bulletproof Multi-Tenancy"
                desc="PostgreSQL 16 row-level security enforces strict contextual isolation at the database tier. Every query is tenant-scoped at the kernel, not the application layer." />
              <ArchCard num="L-03" tag="Compliance" title="Immutable GxP Auditing"
                desc="Append-only audit rules built for 21 CFR Part 11 compliance. Manual modifications are strict architectural no-ops — the ledger is immutable by design, not by convention." />
            </div>
            {/* Right: Telemetry/EKG network graph */}
            <div className="lg:col-span-5 h-full flex items-center justify-center relative">
              <KnowledgeGraph />
            </div>
          </div>

          <div className="mt-20 pt-12 border-t border-white/[0.05] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
            <p className="font-mono text-xs tracking-[0.2em] text-white/70 uppercase max-w-sm">
              Architected for SOC 2, HIPAA &amp; 21 CFR Part 11 workflows
            </p>
            <button onClick={() => setModal("book")}
              className="flex items-center gap-2 border border-[#DEDBC8]/20 hover:border-[#DEDBC8]/50 rounded-full px-6 py-3 text-xs font-medium tracking-widest uppercase text-[#DEDBC8]/80 hover:text-[#DEDBC8] transition-all duration-400">
              Book a Demo
              <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      </section>

      {/* ══════════════════════ CASE STUDIES ══════════════════════ */}
      <CaseStudies />

      {/* ══════════════════════ TESTIMONIALS ══════════════════════ */}
      <Testimonials />

      {/* ══════════════════════ PRICING ══════════════════════ */}
      <Pricing onBook={() => setModal("book")} onSandbox={() => setModal("sandbox")} />

      {/* ══════════════════════ FINAL CTA ══════════════════════ */}
      <FinalCTA onBook={() => setModal("book")} onSandbox={() => setModal("sandbox")} />

      {/* ══════════════════════ FOOTER ══════════════════════ */}
      <footer className="bg-[#060606] border-t border-white/[0.05] py-16 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-10 md:gap-8">
            {/* Brand */}
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2.5">
                <LogoMark size={28} variant="bare" curveColor="#BDD9D7" />
                <span className="font-mono text-xs tracking-[0.35em] text-white/70 uppercase">SANKET</span>
              </div>
              <p className="text-sm text-white/55 leading-relaxed mt-3 max-w-[180px]">
                Demand forecasting for supply chain teams.
              </p>
            </div>

            {/* Product */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Product</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("features")} className="hover:text-[#DEDBC8] transition-colors">Platform</button></li>
                <li><button onClick={() => goToSection("how-it-works")} className="hover:text-[#DEDBC8] transition-colors">How it works</button></li>
                <li><button onClick={() => goToSection("pricing")} className="hover:text-[#DEDBC8] transition-colors">Pricing</button></li>
                <li><button onClick={() => setModal("sandbox")} className="hover:text-[#DEDBC8] transition-colors">Try the sandbox</button></li>
              </ul>
            </div>

            {/* Resources */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Resources</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("architecture")} className="hover:text-[#DEDBC8] transition-colors">Architecture</button></li>
                <li><button onClick={() => goToSection("testimonials")} className="hover:text-[#DEDBC8] transition-colors">Customers</button></li>
                <li><button onClick={() => setModal("book")} className="hover:text-[#DEDBC8] transition-colors">Book a demo</button></li>
                <li><button onClick={() => navigate("/login")} className="hover:text-[#DEDBC8] transition-colors">Sign in</button></li>
              </ul>
            </div>

            {/* Security & Compliance */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Security &amp; Compliance</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("architecture")} className="hover:text-[#DEDBC8] transition-colors">Security overview</button></li>
                <li><span className="text-white/45">Tenant data isolation</span></li>
                <li><span className="text-white/45">GxP audit trails</span></li>
                <li><Link to="/privacy" className="hover:text-[#DEDBC8] transition-colors">Privacy policy</Link></li>
              </ul>
            </div>

            {/* Company */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Company</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("about")} className="hover:text-[#DEDBC8] transition-colors">About</button></li>
                <li><button onClick={() => setModal("book")} className="hover:text-[#DEDBC8] transition-colors">Contact</button></li>
                <li><Link to="/terms" className="hover:text-[#DEDBC8] transition-colors">Terms of service</Link></li>
                <li><Link to="/privacy" className="hover:text-[#DEDBC8] transition-colors">Privacy</Link></li>
              </ul>
            </div>
          </div>

          <div className="mt-14 pt-8 border-t border-white/[0.05] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="font-mono text-[10px] text-white/45 tracking-[0.2em] uppercase">© 2026 SANKET Technologies — All rights reserved</div>
            <div className="font-mono text-[10px] text-white/40 tracking-[0.2em] uppercase">Built for Fashion · Electronics · Pharma · Hardware · Agrocenter</div>
          </div>
        </div>
      </footer>

      {/* ══════════════════════ MODAL ══════════════════════ */}
      <AnimatePresence>
        {modal && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setModal(null)}
            className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4 backdrop-blur-xl"
          >
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.97 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              className="relative w-full max-w-md border border-white/[0.08] bg-[#0A0A0A] rounded-2xl p-7 shadow-2xl"
            >
              <button onClick={() => setModal(null)}
                className="absolute right-5 top-5 w-7 h-7 rounded-full border border-white/[0.08] flex items-center justify-center text-white/30 hover:text-white/70 hover:border-white/20 transition-all outline-none">
                <X size={14} />
              </button>

              <div className="flex gap-4 mb-7 pb-5 border-b border-white/[0.06]">
                {(["book", "sandbox"] as const).map((t) => (
                  <button key={t} onClick={() => setModal(t)}
                    className={`font-mono text-[10px] tracking-[0.2em] uppercase transition-colors ${modal === t ? "text-[#DEDBC8]/80" : "text-white/45 hover:text-white/40"}`}>
                    {t === "book" ? "Book Demo" : "Sandbox"}
                  </button>
                ))}
              </div>

              {modal === "book" ? (
                formSuccess ? (
                  <div className="py-8 text-center">
                    <div className="w-12 h-12 rounded-full border border-[#DEDBC8]/20 flex items-center justify-center mx-auto mb-5 text-[#DEDBC8]/60 text-xl">✓</div>
                    <h3 className="text-base font-light text-white/80 mb-2" style={{ fontFamily: "'DM Serif Display', serif" }}>Request Received</h3>
                    <p className="text-xs text-white/65 leading-relaxed">A specialist will reach out within one business day.</p>
                    <button onClick={() => setModal(null)} className="mt-6 w-full border border-white/[0.08] hover:border-white/20 text-white/30 hover:text-white/60 font-mono text-[10px] tracking-widest uppercase py-3 rounded-lg transition-all outline-none">Dismiss</button>
                  </div>
                ) : (
                  <form onSubmit={submitDemo} className="flex flex-col gap-5">
                    <h3 className="text-lg font-light text-white/80" style={{ fontFamily: "'DM Serif Display', serif" }}>Schedule a Technical Briefing</h3>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <label className="block">
                        <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Full Name</span>
                        <input required value={lead.name} onChange={(e) => setLead({ ...lead, name: e.target.value })} className={inputCls} placeholder="Jane Doe" />
                      </label>
                      <label className="block">
                        <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Work Email</span>
                        <input type="email" required value={lead.email} onChange={(e) => setLead({ ...lead, email: e.target.value })} className={inputCls} placeholder="jane@company.com" />
                      </label>
                    </div>
                    <label className="block">
                      <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Company</span>
                      <input required value={lead.company} onChange={(e) => setLead({ ...lead, company: e.target.value })} className={inputCls} placeholder="Acme Corp" />
                    </label>
                    <label className="block">
                      <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Target Industry</span>
                      <select value={lead.industry} onChange={(e) => setLead({ ...lead, industry: e.target.value })} className={inputCls}>
                        <option value="fashion">Apparel & Fashion</option>
                        <option value="electronics">Consumer Electronics</option>
                        <option value="pharma">Pharmaceuticals</option>
                        <option value="agrocenter">Agrocenter & Farm Inputs</option>
                        <option value="hardware">Tools & Hardware</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Message</span>
                      <textarea value={lead.message} onChange={(e) => setLead({ ...lead, message: e.target.value })} className={`${inputCls} h-14 resize-none`} placeholder="Your forecasting challenges..." />
                    </label>
                    <button type="submit" disabled={formLoading}
                      className="mt-1 w-full bg-[#DEDBC8] hover:bg-[#E8E5D0] text-black font-medium text-xs tracking-widest uppercase py-3.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 transition-all outline-none">
                      {formLoading ? "Sending…" : "Submit Request"} <ArrowRight size={12} />
                    </button>
                  </form>
                )
              ) : (
                <div className="flex flex-col gap-3">
                  <h3 className="text-lg font-light text-white/80 mb-1" style={{ fontFamily: "'DM Serif Display', serif" }}>Explore a Live Sandbox</h3>
                  <p className="font-mono text-[10px] tracking-wide text-white/45 mb-3">Select your industry vertical to launch:</p>
                  {INDUSTRIES.map(({ key, Icon, name }) => (
                    <button key={key} onClick={() => launchSandbox(key)} disabled={launching}
                      className="flex items-center justify-between border border-white/[0.06] hover:border-[#DEDBC8]/20 rounded-lg px-4 py-3 text-xs text-white/40 hover:text-white/70 transition-all disabled:opacity-40 outline-none">
                      <span className="flex items-center gap-3"><Icon size={14} className="text-[#DEDBC8]/30" />{name}</span>
                      <ArrowRight size={12} className="text-white/15" />
                    </button>
                  ))}
                  {launching && (
                    <div className="flex items-center justify-center gap-2 mt-2 text-[11px] font-mono text-[#DEDBC8]/40">
                      <RefreshCw size={12} className="animate-spin" /> Authenticating…
                    </div>
                  )}
                </div>
              )}

              <div className="mt-6 pt-4 border-t border-white/[0.06] flex items-center justify-between text-[10px] font-mono tracking-wider">
                <button onClick={() => { setModal(null); navigate("/login?mode=signup"); }} className="text-white/30 hover:text-white/60 transition-all uppercase outline-none">
                  Create Account
                </button>
                <div className="w-px h-2 bg-white/10" />
                <button onClick={() => { setModal(null); navigate("/login"); }} className="text-[#DEDBC8]/60 hover:text-[#DEDBC8] transition-all uppercase font-medium outline-none">
                  Existing customer? Sign in
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

