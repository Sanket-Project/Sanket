import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Check,
  CircleAlert,
  Plug,
  ShieldCheck,
  Sparkles,
} from "@/components/ui/icons";
import { LogoMark } from "@/components/ui/Logo";
import { CONNECTORS } from "./connectors";
import "./live-console.css";
import { ConnectorGrid } from "./sections/ConnectorGrid";
import { ForecastEngine } from "./sections/ForecastEngine";
import { IndustryTabs } from "./sections/IndustryTabs";
import { ModuleGrid } from "./sections/ModuleGrid";
import { SecurityTenancy } from "./sections/SecurityTenancy";
import { SignalGrid } from "./sections/SignalGrid";
import { WhatItDoes } from "./sections/WhatItDoes";

type LiveConsoleLandingProps = {
  onBook: () => void;
  onSandbox: () => void;
};

/* ------------------------------------------------------------------ */
/*  Small hooks that drive the product surfaces                        */
/* ------------------------------------------------------------------ */

/**
 * Fires once when the element first reaches the lower band of the viewport.
 *
 * Deliberately not IntersectionObserver, and not scroll-event-only: both go
 * silent in browsers that are not compositing frames, which would leave every
 * revealed block stuck invisible. A short poll always resolves, and clears
 * itself the moment the element has been seen.
 */
const useInViewOnce = <T extends HTMLElement>(band = 0.85) => {
  const ref = useRef<T | null>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    if (seen) return undefined;
    const node = ref.current;
    if (!node) return undefined;

    let raf = 0;
    const check = () => {
      const rect = node.getBoundingClientRect();
      if (rect.top < window.innerHeight * band && rect.bottom > 0) setSeen(true);
    };
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(check);
    };

    check();
    const poll = window.setInterval(check, 160);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.clearInterval(poll);
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [seen, band]);

  return [ref, seen] as const;
};

/** Types a string out one character at a time once `active` is true. */
const useTypewriter = (text: string, active: boolean, speed = 26, skip = false) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!active) return undefined;
    if (skip) {
      setCount(text.length);
      return undefined;
    }
    if (count >= text.length) return undefined;
    const id = window.setTimeout(() => setCount((c) => c + 1), speed);
    return () => window.clearTimeout(id);
  }, [active, skip, count, text.length, speed]);

  return {
    shown: text.slice(0, count),
    done: count >= text.length,
  };
};

/** Advances an index on an interval, stopping at `length`. */
const useStepper = (length: number, active: boolean, interval: number, skip = false) => {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!active) return undefined;
    if (skip) {
      setStep(length);
      return undefined;
    }
    if (step >= length) return undefined;
    const id = window.setTimeout(() => setStep((s) => s + 1), interval);
    return () => window.clearTimeout(id);
  }, [active, skip, step, length, interval]);

  return step;
};

/* ------------------------------------------------------------------ */
/*  Content                                                            */
/* ------------------------------------------------------------------ */

const SIGNALS = [
  { title: "Stockout risk · SKU-8820", meta: "4 days of cover left", level: "Urgent" },
  { title: "Demand spike · North zone", meta: "+34% vs forecast", level: "High" },
  { title: "Supplier slip · Vendor 114", meta: "ETA moved +6 days", level: "Medium" },
];

const SYSTEMS = [
  { name: "Shopify", detail: "8,412 orders" },
  { name: "PostgreSQL", detail: "Inventory ledger" },
  { name: "WooCommerce", detail: "2,190 orders" },
  { name: "Unicommerce", detail: "Fulfilment" },
];

const NETWORK = [
  { label: "Days of cover", value: "4.0", tone: "warn" },
  { label: "Forecast accuracy", value: "89.9%", tone: "ok" },
  { label: "SKUs tracked", value: "1,240", tone: "flat" },
  { label: "Open decisions", value: "3", tone: "flat" },
];

const CONSOLE_QUERY = "SKU-8820 is down to 4 days of cover. What should I reorder?";

const DRIVERS = [
  { rank: "1", title: "Festive demand pull · North", detail: "Search + promotion signal", weight: 89, delta: "+18%" },
  { rank: "2", title: "Vendor 114 lead-time slip", detail: "Confirmed ETA moved", weight: 84, delta: "+6d" },
  { rank: "3", title: "Size-curve drift · M / L", detail: "Returns-adjusted mix", weight: 71, delta: "−9%" },
];

const DECISIONS = [
  { id: "PO-2201", title: "Reorder 1,800 units", detail: "Vendor 114 · lead time 21d" },
  { id: "TRF-8841", title: "Transfer 240 units", detail: "Pune DC → Delhi DC" },
  { id: "MKD-0417", title: "Hold markdown", detail: "Line 22 · review in 7d" },
];

const STATS = [
  { value: "5", label: "Industries served", detail: "Fashion, electronics, pharma, hardware, and agro run on the same engine." },
  { value: "6", label: "Live connectors", detail: "Shopify, WooCommerce, PostgreSQL, MySQL, CSV and Excel work today; the catalog holds 42." },
  { value: "90d", label: "Forecast horizon", detail: "Daily SKU-level demand with a visible confidence range, not a single number." },
];

/* ------------------------------------------------------------------ */
/*  Reveal wrapper                                                     */
/* ------------------------------------------------------------------ */

// Driven by the rect hook rather than whileInView: IntersectionObserver does
// not report in browsers that are not compositing frames, and a reveal that
// never fires would leave the content invisible.
const Reveal = ({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) => {
  const reduce = useReducedMotion();
  const [ref, seen] = useInViewOnce<HTMLDivElement>(0.92);
  const visible = seen || !!reduce;

  return (
    <div
      ref={ref}
      className={`lc-reveal${visible ? " is-in" : ""}${className ? ` ${className}` : ""}`}
      style={visible && delay ? { transitionDelay: `${delay}s` } : undefined}
    >
      {children}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  The console surface                                                */
/* ------------------------------------------------------------------ */

const ConsoleSurface = () => {
  const reduce = useReducedMotion();
  const [ref, seen] = useInViewOnce<HTMLDivElement>();

  // systems and signals populate concurrently, then the question is asked
  const online = useStepper(SYSTEMS.length, seen, 430, !!reduce);
  const signals = useStepper(SIGNALS.length, seen, 400, !!reduce);

  const typingActive = seen && signals >= SIGNALS.length;
  const { shown, done } = useTypewriter(CONSOLE_QUERY, typingActive, 17, !!reduce);
  const [answered, setAnswered] = useState(false);

  useEffect(() => {
    if (!done) return undefined;
    if (reduce) {
      setAnswered(true);
      return undefined;
    }
    const id = window.setTimeout(() => setAnswered(true), 520);
    return () => window.clearTimeout(id);
  }, [done, reduce]);

  return (
    <div className="lc-console" ref={ref}>
      <div className="lc-chrome">
        <span className="lc-dots" aria-hidden="true"><i /><i /><i /></span>
        <span className="lc-url">app.sanket.ai/console</span>
        <span className={`lc-live ${seen ? "is-on" : ""}`}>
          <i aria-hidden="true" />
          Live
        </span>
      </div>

      <div className="lc-console-body">
        <div className="lc-panel lc-panel-signals">
          <p className="lc-panel-title">Active signals</p>
          <ul>
            {SIGNALS.map((signal, i) => (
              <li key={signal.title} className={i < signals ? "is-in" : ""}>
                <span className="lc-signal-copy">
                  <strong>{signal.title}</strong>
                  <small>{signal.meta}</small>
                </span>
                <span className={`lc-badge lc-badge-${signal.level.toLowerCase()}`}>{signal.level}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="lc-panel lc-panel-systems">
          <p className="lc-panel-title">Connected systems</p>
          <ul>
            {SYSTEMS.map((system, i) => {
              const state = i < online ? "live" : i === online ? "syncing" : "waiting";
              return (
                <li key={system.name}>
                  <span className="lc-signal-copy">
                    <strong>{system.name}</strong>
                    <small>{system.detail}</small>
                  </span>
                  <span className={`lc-state lc-state-${state}`}>
                    {state === "live" ? <Check size={12} aria-hidden="true" /> : null}
                    {state === "live" ? "Live" : state === "syncing" ? "Syncing" : "Waiting"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="lc-panel lc-panel-network">
          <p className="lc-panel-title">Network</p>
          <div className="lc-tiles">
            {NETWORK.map((tile) => (
              <div key={tile.label} className={`lc-tile lc-tile-${tile.tone}`}>
                <span>{tile.label}</span>
                <strong>{tile.value}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="lc-ask">
          <p className="lc-panel-title">Ask Sanket</p>
          <p className="lc-query">
            <span className="lc-caret-line">
              {shown}
              {!done && typingActive ? <i className="lc-caret" aria-hidden="true" /> : null}
            </span>
          </p>

          <div className={`lc-answer ${answered ? "is-in" : ""}`} aria-live="polite">
            <span className="lc-answer-icon" aria-hidden="true"><Sparkles size={14} /></span>
            <div>
              <strong>Reorder 1,800 units from Vendor 114 by 04 Jun.</strong>
              <small>
                Covers the 21-day lead time and the festive pull in the north zone. Stockout avoided
                on 17 Jul at the current run rate.
              </small>
            </div>
            <span className="lc-conf">89% confidence</span>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Driver ranking surface                                             */
/* ------------------------------------------------------------------ */

const DriverSurface = () => {
  const reduce = useReducedMotion();
  const [ref, seen] = useInViewOnce<HTMLDivElement>();

  return (
    <div className="lc-surface" ref={ref}>
      <div className="lc-surface-head">
        <span className="lc-surface-url">app.sanket.ai/forecast</span>
        <span className="lc-surface-tag">Why the forecast moved</span>
      </div>
      <ul className="lc-drivers">
        {DRIVERS.map((driver, i) => (
          <li key={driver.rank}>
            <span className="lc-rank">{driver.rank}</span>
            <span className="lc-driver-copy">
              <strong>{driver.title}</strong>
              <small>{driver.detail}</small>
            </span>
            <span className="lc-meter" aria-hidden="true">
              <motion.i
                initial={reduce ? false : { width: 0 }}
                animate={{ width: seen ? `${driver.weight}%` : 0 }}
                transition={{ duration: 0.85, delay: 0.15 + i * 0.12, ease: [0.16, 1, 0.3, 1] }}
              />
            </span>
            <span className="lc-driver-num">{driver.weight}</span>
            <span className="lc-driver-delta">{driver.delta}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Decision queue surface                                             */
/* ------------------------------------------------------------------ */

const DecisionSurface = () => {
  const reduce = useReducedMotion();
  const [ref, seen] = useInViewOnce<HTMLDivElement>();
  const approved = useStepper(DECISIONS.length, seen, 700, !!reduce);

  return (
    <div className="lc-surface" ref={ref}>
      <div className="lc-surface-head">
        <span className="lc-surface-url">app.sanket.ai/decisions</span>
        <span className="lc-surface-tag">Queued for review</span>
      </div>
      <ul className="lc-decisions">
        {DECISIONS.map((decision, i) => (
          <li key={decision.id}>
            <span className="lc-decision-id">{decision.id}</span>
            <span className="lc-driver-copy">
              <strong>{decision.title}</strong>
              <small>{decision.detail}</small>
            </span>
            <span className={`lc-status ${i < approved ? "is-approved" : ""}`}>
              {i < approved ? <Check size={12} aria-hidden="true" /> : null}
              {i < approved ? "Approved" : "Pending"}
            </span>
          </li>
        ))}
      </ul>
      <p className="lc-surface-foot">
        Every approval is written to the audit trail with the evidence it was based on.
      </p>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Connector surface                                                  */
/* ------------------------------------------------------------------ */

const ConnectSurface = () => {
  const reduce = useReducedMotion();
  const [ref, seen] = useInViewOnce<HTMLDivElement>();
  const linked = useStepper(6, seen, 420, !!reduce);
  const shown = useMemo(() => CONNECTORS.slice(0, 6), []);

  return (
    <div className="lc-surface" ref={ref}>
      <div className="lc-surface-head">
        <span className="lc-surface-url">app.sanket.ai/connect</span>
        <span className="lc-surface-tag">
          {linked < shown.length ? `Linking ${shown[linked].name}…` : "All sources linked"}
        </span>
      </div>
      <ul className="lc-links">
        {shown.map((connector, i) => (
          <li key={connector.name} className={i < linked ? "is-linked" : ""}>
            <span className="lc-link-dot" aria-hidden="true" />
            {connector.name}
            <span className="lc-link-state">{i < linked ? "Linked" : i === linked ? "Linking" : "Queued"}</span>
          </li>
        ))}
      </ul>
      <p className="lc-surface-foot">No migration. Sanket reads what your systems already record.</p>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export const LiveConsoleLanding = ({ onBook, onSandbox }: LiveConsoleLandingProps) => {
  // Industry selection moved into <IndustryTabs />, which reads the real
  // per-vertical planning profile from content.ts rather than the abbreviated
  // copy that used to live in this file.
  return (
    <main className="lc">
      {/* ── Console ─────────────────────────────────────────── */}
      <section id="platform" className="lc-section lc-section-console">
        <div className="lc-shell">
          <Reveal className="lc-intro">
            <p className="lc-kicker">Live console</p>
            <h2 className="lc-h2">
              See what your demand is doing, <em>and what to do about it.</em>
            </h2>
            <p className="lc-lede">
              Sanket reads your orders, stock, and supplier signals as they land, ranks what is
              actually moving demand, and turns it into an order you can approve.
            </p>
          </Reveal>

          <Reveal delay={0.08}>
            <ConsoleSurface />
          </Reveal>

          <Reveal delay={0.12} className="lc-note-row">
            <span><Plug size={15} aria-hidden="true" />Connects to the systems you already run</span>
            <span><ShieldCheck size={15} aria-hidden="true" />Every decision carries its evidence</span>
            <span><CircleAlert size={15} aria-hidden="true" />Illustrative data shown</span>
          </Reveal>
        </div>
      </section>

      <WhatItDoes />

      {/* ── Capabilities ────────────────────────────────────── */}
      <section id="how-it-works" className="lc-section lc-section-alt">
        <div className="lc-shell lc-stack">
          <div className="lc-split">
            <Reveal className="lc-split-copy">
              <p className="lc-kicker">Forecast</p>
              <h3 className="lc-h3">Ranked drivers, not another chart</h3>
              <p className="lc-body">
                Sanket scores what moved the forecast — promotions, lead-time slips, size-curve
                drift — so your team argues about levers instead of lagging dashboards.
              </p>
              <button type="button" className="lc-link-btn" onClick={onSandbox}>
                Open the sandbox <ArrowRight size={15} aria-hidden="true" />
              </button>
            </Reveal>
            <Reveal delay={0.08} className="lc-split-surface">
              <DriverSurface />
            </Reveal>
          </div>

          <div className="lc-split is-reversed">
            <Reveal className="lc-split-copy">
              <p className="lc-kicker">Connect</p>
              <h3 className="lc-h3">One picture from every source</h3>
              <p className="lc-body">
                Storefronts, ERPs, databases, and logistics partners sync into a single view. No
                data entry, no re-platforming, no reconciliation before a decision.
              </p>
              <Link className="lc-link-btn" to="/login">
                Connect a source <ArrowRight size={15} aria-hidden="true" />
              </Link>
            </Reveal>
            <Reveal delay={0.08} className="lc-split-surface">
              <ConnectSurface />
            </Reveal>
          </div>

          <div className="lc-split">
            <Reveal className="lc-split-copy">
              <p className="lc-kicker">Decide</p>
              <h3 className="lc-h3">Actions your team can approve</h3>
              <p className="lc-body">
                Reorders, transfers, and markdown holds arrive as concrete quantities and dates,
                each with the evidence behind it and a record of who approved what.
              </p>
              <button type="button" className="lc-link-btn" onClick={onBook}>
                See it on your data <ArrowRight size={15} aria-hidden="true" />
              </button>
            </Reveal>
            <Reveal delay={0.08} className="lc-split-surface">
              <DecisionSurface />
            </Reveal>
          </div>
        </div>
      </section>

      <IndustryTabs />

      <ModuleGrid />

      <SignalGrid />

      <ConnectorGrid />

      <ForecastEngine />

      <SecurityTenancy />

      {/* ── Stats + CTA ─────────────────────────────────────── */}
      <section id="get-started" className="lc-section lc-section-alt">
        <div className="lc-shell">
          <Reveal className="lc-stats">
            {STATS.map((stat) => (
              <article key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
                <p>{stat.detail}</p>
              </article>
            ))}
          </Reveal>

          <Reveal delay={0.08} className="lc-cta">
            <div>
              <h2 className="lc-h2">Stop guessing. Start deciding.</h2>
              <p className="lc-lede">
                Bring one month of sales history. We will show you the forecast, the drivers behind
                it, and the first order it recommends.
              </p>
            </div>
            <div className="lc-cta-actions">
              <button type="button" className="lc-btn lc-btn-primary" onClick={onBook}>
                Book a demo <ArrowRight size={16} aria-hidden="true" />
              </button>
              <button type="button" className="lc-btn" onClick={onSandbox}>
                Try the sandbox
              </button>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────── */}
      <footer className="lc-footer">
        <div className="lc-shell">
          <div className="lc-footer-top">
            <div className="lc-footer-brand">
              <LogoMark size={28} variant="bare" curveColor="#03363D" />
              <span>SANKET</span>
              <p>Demand forecasting and inventory decisions for supply-chain teams.</p>
            </div>
            <nav aria-label="Footer navigation">
              <a href="#features">Console</a>
              <a href="#how-it-works">How it works</a>
              <a href="#architecture">Industries</a>
              <button type="button" onClick={onBook}>Book a demo</button>
              <Link to="/terms">Terms</Link>
              <Link to="/privacy">Privacy</Link>
            </nav>
          </div>
          <div className="lc-footer-bottom">
            <span>© 2026 Sanket Technologies</span>
            <span>Fashion · Electronics · Pharma · Hardware · Agrocenter</span>
          </div>
        </div>
      </footer>
    </main>
  );
};
