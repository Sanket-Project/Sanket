import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Boxes,
  CalendarClock,
  Check,
  CircleDot,
  Database,
  FileSpreadsheet,
  Gauge,
  PackageCheck,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
  Truck,
} from "@/components/ui/icons";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { LogoMark } from "@/components/ui/Logo";
import "./models-disagree.css";

type ModelsDisagreeLandingProps = {
  onBook: () => void;
  onSandbox: () => void;
};

type ModelKey = "statistical" | "causal" | "hybrid" | "sequence";
type ScenarioKey = "lean" | "balanced" | "service";
type IndustryKey = "fashion" | "electronics" | "pharma" | "hardware" | "agrocenter";

type ForecastPoint = {
  date: string;
  actual: number | null;
  statistical: number | null;
  causal: number | null;
  hybrid: number | null;
  sequence: number | null;
  range: [number, number] | null;
};

const FORECAST_DATA: ForecastPoint[] = [
  { date: "Feb 25", actual: 440, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Mar 04", actual: 505, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Mar 11", actual: 472, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Mar 18", actual: 590, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Mar 25", actual: 535, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Apr 01", actual: 642, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Apr 08", actual: 548, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Apr 15", actual: 674, statistical: null, causal: null, hybrid: null, sequence: null, range: null },
  { date: "Apr 22", actual: 612, statistical: 612, causal: 612, hybrid: 612, sequence: 612, range: [612, 612] },
  { date: "May 01", actual: null, statistical: 658, causal: 624, hybrid: 650, sequence: 590, range: [540, 715] },
  { date: "May 10", actual: null, statistical: 694, causal: 651, hybrid: 690, sequence: 546, range: [490, 778] },
  { date: "May 19", actual: null, statistical: 731, causal: 680, hybrid: 728, sequence: 505, range: [435, 842] },
  { date: "May 28", actual: null, statistical: 766, causal: 708, hybrid: 762, sequence: 452, range: [380, 905] },
  { date: "Jun 06", actual: null, statistical: 809, causal: 736, hybrid: 801, sequence: 396, range: [320, 972] },
  { date: "Jun 15", actual: null, statistical: 850, causal: 756, hybrid: 838, sequence: 338, range: [260, 1035] },
  { date: "Jun 24", actual: null, statistical: 886, causal: 774, hybrid: 872, sequence: 278, range: [205, 1098] },
  { date: "Jul 03", actual: null, statistical: 928, causal: 795, hybrid: 908, sequence: 212, range: [150, 1160] },
];

const MODELS: Array<{
  key: ModelKey;
  label: string;
  approach: string;
  dash?: string;
  stroke: string;
}> = [
  { key: "statistical", label: "Statistical", approach: "Trend + seasonality", stroke: "#b7b1a0" },
  { key: "causal", label: "Context", approach: "Price + calendar + signals", stroke: "#c79548", dash: "8 5" },
  { key: "hybrid", label: "Hybrid", approach: "State space + regression", stroke: "#bdd9d7" },
  { key: "sequence", label: "Sequence", approach: "Recent-pattern sensitivity", stroke: "#6d8583", dash: "3 5" },
];

const STAGES = [
  {
    label: "Model divergence",
    short: "Candidates start apart",
    description: "Each candidate carries different assumptions about seasonality, context, and recent demand.",
    Icon: Activity,
  },
  {
    label: "Evidence arrives",
    short: "Signals gain context",
    description: "Fresh inventory, market, and supplier evidence is aligned to the same decision window.",
    Icon: ScanSearch,
  },
  {
    label: "Weights adjust",
    short: "Validation changes influence",
    description: "Recent error and data quality determine how much influence each candidate receives.",
    Icon: SlidersHorizontal,
  },
  {
    label: "Decision corridor",
    short: "Uncertainty becomes usable",
    description: "Sanket keeps the range visible, then converts it into an order window your team can review.",
    Icon: Gauge,
  },
];

const MODEL_WEIGHTS: Array<Record<ModelKey, number>> = [
  { statistical: 0.25, causal: 0.25, hybrid: 0.25, sequence: 0.25 },
  { statistical: 0.24, causal: 0.27, hybrid: 0.28, sequence: 0.21 },
  { statistical: 0.18, causal: 0.27, hybrid: 0.33, sequence: 0.22 },
  { statistical: 0.13, causal: 0.26, hybrid: 0.42, sequence: 0.19 },
];

// Evidence that lands on the timeline from stage 2 onwards.
const EVIDENCE_MARKERS: Array<{ date: string; y: number; label: string }> = [
  { date: "Mar 18", y: 590, label: "Promotion" },
  { date: "Apr 08", y: 548, label: "Price change" },
  { date: "Apr 22", y: 612, label: "Supplier ETA" },
];

const HISTORICAL_ERRORS: Record<ModelKey, string> = {
  statistical: "18.7%",
  causal: "14.3%",
  hybrid: "10.1%",
  sequence: "13.9%",
};

const MODEL_NOTES: Record<ModelKey, string> = {
  statistical: "Reliable baseline; slower around promotions.",
  causal: "Responds well when external context is fresh.",
  hybrid: "Best calibrated for this illustrative window.",
  sequence: "Sensitive to short-term changes and sparse history.",
};

const INDUSTRIES: Array<{
  key: IndustryKey;
  number: string;
  label: string;
  observes: string;
  risk: string;
  action: string;
}> = [
  {
    key: "fashion",
    number: "01",
    label: "Fashion",
    observes: "SKU, size curve, returns, promotion cadence",
    risk: "A regional search spike precedes store sales.",
    action: "Rebalance by size before replenishing the whole line.",
  },
  {
    key: "electronics",
    number: "02",
    label: "Electronics",
    observes: "SKU, launch cycle, channel, price movement",
    risk: "A price move changes demand before channel reports settle.",
    action: "Advance the order window without overcommitting stock.",
  },
  {
    key: "pharma",
    number: "03",
    label: "Pharma",
    observes: "Product, region, expiry profile, supply availability",
    risk: "Regional demand rises while usable stock narrows.",
    action: "Prioritize allocation and keep the decision traceable.",
  },
  {
    key: "hardware",
    number: "04",
    label: "Hardware",
    observes: "Item, branch, project demand, supplier lead time",
    risk: "A lead-time shift creates a hidden coverage gap.",
    action: "Move the last safe order date forward.",
  },
  {
    key: "agrocenter",
    number: "05",
    label: "Agrocenter",
    observes: "Product, season, weather context, location",
    risk: "Weather context reshapes the expected seasonal peak.",
    action: "Stage inventory by region instead of applying one curve.",
  },
];

const SCENARIOS: Array<{
  key: ScenarioKey;
  name: string;
  principle: string;
  service: string;
  inventory: string;
  stockouts: string;
  capital: string;
  note: string;
}> = [
  {
    key: "lean",
    name: "Lean",
    principle: "Working capital first",
    service: "90%",
    inventory: "−22%",
    stockouts: "2",
    capital: "−18%",
    note: "Lower inventory, with more exposure to late demand shifts.",
  },
  {
    key: "balanced",
    name: "Balanced",
    principle: "Default decision",
    service: "95%",
    inventory: "Baseline",
    stockouts: "0",
    capital: "Baseline",
    note: "Best trade-off across availability, risk, and cash in this scenario.",
  },
  {
    key: "service",
    name: "Service",
    principle: "Availability first",
    service: "98%",
    inventory: "+24%",
    stockouts: "0",
    capital: "+19%",
    note: "Higher inventory protects service when availability matters most.",
  },
];

// Read as one continuous audit trail rather than four parallel feature cards:
// where a signal came from, how it arrived, how it was recorded, what was checked.
const EVIDENCE_TRACE = [
  {
    step: "01",
    label: "Signal families",
    Icon: Database,
    items: ["Sales · Inventory · Returns", "Price · Promotion · Calendar", "Search · Weather · Economic", "Supplier ETA · Lead time"],
  },
  {
    step: "02",
    label: "Arrives via",
    Icon: FileSpreadsheet,
    items: ["Files", "Shopify", "WooCommerce", "PostgreSQL", "MySQL", "REST + webhooks (beta)"],
  },
  {
    step: "03",
    label: "Recorded as",
    Icon: CircleDot,
    items: ["source = sales_feed", "field = units_sold", "frequency = daily", "window = 90 days"],
  },
  {
    step: "04",
    label: "Checked for",
    Icon: ShieldCheck,
    items: ["Completeness", "Freshness", "Schema", "Outliers reviewed"],
  },
];

const formatWeight = (value: number) => `${Math.round(value * 100)}%`;

export const ModelsDisagreeLanding = ({ onBook, onSandbox }: ModelsDisagreeLandingProps) => {
  const reduceMotion = useReducedMotion();
  const [stage, setStage] = useState(0);
  const [industry, setIndustry] = useState<IndustryKey>("fashion");
  const [scenario, setScenario] = useState<ScenarioKey>("balanced");

  const activeIndustry = useMemo(
    () => INDUSTRIES.find((item) => item.key === industry) ?? INDUSTRIES[0],
    [industry],
  );
  const activeScenario = useMemo(
    () => SCENARIOS.find((item) => item.key === scenario) ?? SCENARIOS[1],
    [scenario],
  );
  const weights = MODEL_WEIGHTS[stage];

  // The chart has to perform the argument, not just caption it: candidates
  // diverge, evidence lands, weights move, and only then does the corridor
  // resolve into a single decision path.
  const chartData = useMemo(
    () =>
      FORECAST_DATA.map((point) => {
        const complete = MODELS.every((model) => point[model.key] !== null);
        return {
          ...point,
          blend:
            stage === 3 && complete
              ? Math.round(
                  MODELS.reduce((sum, model) => sum + (point[model.key] as number) * weights[model.key], 0),
                )
              : null,
          range: stage === 3 ? point.range : null,
        };
      }),
    [stage, weights],
  );

  // Stage 0-1 show the candidates as equals. Stage 2 lets weight drive
  // prominence. Stage 3 retires them behind the blended path.
  const candidateStyle = useCallback(
    (key: ModelKey) => {
      if (stage === 3) return { opacity: 0.16, width: 1 };
      if (stage === 2) return { opacity: 0.34 + weights[key] * 1.9, width: 1 + weights[key] * 4.2 };
      return { opacity: 0.95, width: 1.5 };
    },
    [stage, weights],
  );

  const instrumentRef = useRef<HTMLDivElement | null>(null);
  const [autoPlaying, setAutoPlaying] = useState(false);
  const [userDrove, setUserDrove] = useState(false);

  const selectStage = useCallback((index: number) => {
    setUserDrove(true);
    setStage(index);
  }, []);

  // Play the sequence once when the chart first comes into view so the argument
  // tells itself; any click hands control back to the reader for good. A rect
  // check rather than IntersectionObserver, which does not report in browsers
  // that are not compositing frames.
  useEffect(() => {
    if (reduceMotion || userDrove || autoPlaying) return undefined;
    const node = instrumentRef.current;
    if (!node) return undefined;

    const check = () => {
      const rect = node.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.75 && rect.bottom > window.innerHeight * 0.25) {
        setAutoPlaying(true);
      }
    };

    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, [reduceMotion, userDrove, autoPlaying]);

  useEffect(() => {
    if (!autoPlaying || userDrove || stage >= STAGES.length - 1) return undefined;
    const id = window.setTimeout(() => setStage((current) => Math.min(current + 1, STAGES.length - 1)), 1800);
    return () => window.clearTimeout(id);
  }, [autoPlaying, userDrove, stage]);

  return (
    <main className="mdx-landing">
      <section id="features" className="mdx-ensemble" aria-labelledby="ensemble-title">
        <div className="mdx-shell">
          <div className="mdx-ensemble-intro">
            <div>
              <p className="mdx-kicker">01 / Calibrated uncertainty</p>
              <h2 id="ensemble-title" className="mdx-display">
                Forecasts should disagree.
                <em>Reality does.</em>
              </h2>
            </div>
            <p className="mdx-intro-copy">
              Different models see the same signal differently. Sanket lets them compete, then uses evidence—not opinion—to build a decision range.
            </p>
            <dl className="mdx-demo-meta" aria-label="Demo scenario details">
              <div><dt>Demo scenario</dt><dd>Camp lantern · 001</dd></div>
              <div><dt>Market</dt><dd>North America</dd></div>
              <div><dt>Horizon</dt><dd>90 days</dd></div>
              <div><dt>As of</dt><dd>26 Aug 2026</dd></div>
            </dl>
          </div>

          <div className="mdx-instrument" id="how-it-works">
            <div className="mdx-instrument-head">
              <div>
                <span>Ensemble forecast</span>
                <strong>Four candidates. One decision corridor.</strong>
              </div>
              <div className="mdx-legend" aria-label="Forecast model legend">
                {MODELS.map((model) => (
                  <span key={model.key}>
                    <i style={{ borderColor: model.stroke, borderStyle: model.dash ? "dashed" : "solid" }} />
                    {model.label}
                  </span>
                ))}
                {stage === 3 ? (
                  <span className="mdx-legend-result">
                    <i style={{ borderColor: "#e8e5d0", borderStyle: "dashed" }} />
                    Decision path
                  </span>
                ) : null}
              </div>
            </div>

            <div className="mdx-chart-wrap" ref={instrumentRef} role="img" aria-label={`Illustrative ensemble forecast, step ${stage + 1} of ${STAGES.length}: ${STAGES[stage].label}. ${STAGES[stage].description}`}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 34, right: 26, bottom: 8, left: -12 }}>
                  <CartesianGrid stroke="rgba(222,219,200,0.09)" strokeDasharray="2 6" vertical={false} />
                  <XAxis
                    dataKey="date"
                    axisLine={{ stroke: "rgba(222,219,200,0.18)" }}
                    tickLine={false}
                    tick={{ fill: "rgba(232,229,208,0.58)", fontSize: 10, fontFamily: "IBM Plex Mono" }}
                    interval={2}
                  />
                  <YAxis
                    width={48}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "rgba(232,229,208,0.52)", fontSize: 10, fontFamily: "IBM Plex Mono" }}
                    domain={[100, 1200]}
                  />
                  <Tooltip
                    cursor={{ stroke: "rgba(189,217,215,0.25)", strokeDasharray: "3 5" }}
                    contentStyle={{
                      border: "1px solid rgba(189,217,215,0.18)",
                      borderRadius: 0,
                      background: "#09100f",
                      color: "#e8e5d0",
                      fontFamily: "IBM Plex Mono",
                      fontSize: 11,
                    }}
                    labelStyle={{ color: "#bdd9d7", marginBottom: 8 }}
                  />
                  <ReferenceLine
                    x="Apr 22"
                    stroke="rgba(232,229,208,0.38)"
                    strokeDasharray="3 4"
                    label={{ value: "FORECAST", position: "insideTopLeft", fill: "rgba(232,229,208,0.6)", fontSize: 9 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="range"
                    stroke="none"
                    fill="#c79548"
                    fillOpacity={0.15}
                    isAnimationActive={!reduceMotion}
                    animationDuration={520}
                  />
                  <Line type="monotone" dataKey="actual" name="Observed sales" stroke="#e8e5d0" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={!reduceMotion} />
                  {MODELS.map((model) => {
                    const style = candidateStyle(model.key);
                    return (
                      <Line
                        key={model.key}
                        type="monotone"
                        dataKey={model.key}
                        name={model.label}
                        stroke={model.stroke}
                        strokeWidth={style.width}
                        strokeDasharray={model.dash}
                        strokeOpacity={style.opacity}
                        dot={false}
                        isAnimationActive={!reduceMotion}
                        animationDuration={520}
                      />
                    );
                  })}
                  <Line
                    type="monotone"
                    dataKey="blend"
                    name="Weighted decision path"
                    stroke="#e8e5d0"
                    strokeWidth={2.6}
                    strokeDasharray="9 6"
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={!reduceMotion}
                    animationDuration={620}
                  />
                  {stage >= 1 &&
                    EVIDENCE_MARKERS.map((marker) => (
                      <ReferenceDot
                        key={marker.label}
                        x={marker.date}
                        y={marker.y}
                        r={3.5}
                        fill="#09100f"
                        stroke="#bdd9d7"
                        strokeWidth={1.5}
                        isFront
                        label={{
                          value: marker.label,
                          position: "top",
                          offset: 12,
                          fill: "rgba(189,217,215,0.82)",
                          fontSize: 11,
                          fontFamily: "IBM Plex Mono",
                        }}
                      />
                    ))}
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <div className="mdx-stage-strip" aria-label="Forecast reasoning stages">
              {STAGES.map(({ label, short, Icon }, index) => (
                <button
                  key={label}
                  type="button"
                  className={stage === index ? "is-active" : ""}
                  aria-pressed={stage === index}
                  onClick={() => selectStage(index)}
                >
                  <Icon size={18} aria-hidden="true" />
                  <span><strong>{label}</strong><small>{short}</small></span>
                  <b>{String(index + 1).padStart(2, "0")}</b>
                </button>
              ))}
            </div>

            <div className="mdx-stage-explanation" aria-live="polite">
              <span>Current reading</span>
              <AnimatePresence mode="wait" initial={false}>
                <motion.p
                  key={stage}
                  initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
                  transition={{ duration: 0.24 }}
                >
                  {STAGES[stage].description}
                </motion.p>
              </AnimatePresence>
            </div>

            <div className="mdx-model-table" role="table" aria-label="Illustrative model comparison">
              <div className="mdx-model-row mdx-model-head" role="row">
                <span role="columnheader">Model candidate</span>
                <span role="columnheader">Approach</span>
                <span role="columnheader">Weight now</span>
                <span role="columnheader">Historical error</span>
                <span role="columnheader">Why it wins or loses</span>
              </div>
              {MODELS.map((model) => (
                <div className={`mdx-model-row ${model.key === "hybrid" && stage >= 2 ? "is-leading" : ""}`} role="row" key={model.key}>
                  <strong role="cell" data-label="Model">{model.label}</strong>
                  <span role="cell" data-label="Approach">{model.approach}</span>
                  <span role="cell" data-label="Weight"><i className="mdx-weight"><b style={{ width: formatWeight(weights[model.key]) }} /></i>{formatWeight(weights[model.key])}</span>
                  <span role="cell" data-label="Error">{HISTORICAL_ERRORS[model.key]}</span>
                  <span role="cell" data-label="Reading">{MODEL_NOTES[model.key]}</span>
                </div>
              ))}
            </div>

            <div className="mdx-outcome-strip" aria-label="Illustrative forecast outcome">
              <div><CalendarClock size={18} /><span>Projected stockout</span><strong>17 Jul 2026</strong></div>
              <div><PackageCheck size={18} /><span>Last safe order date</span><strong>04 Jun 2026</strong></div>
              <div><Boxes size={18} /><span>Current on hand</span><strong>1,240 units</strong></div>
              <div><Truck size={18} /><span>Incoming confirmed</span><strong>600 units</strong></div>
            </div>
            <p className="mdx-disclaimer">Illustrative scenario for product demonstration. Forecast values are not a guarantee of future results.</p>
          </div>
        </div>
      </section>

      <section id="architecture" className="mdx-evidence" aria-labelledby="evidence-title">
        <div className="mdx-shell">
          <div className="mdx-evidence-titlebar">
            <div>
              <p className="mdx-kicker mdx-kicker-dark">02 / Evidence ledger</p>
              <h2 id="evidence-title">Evidence that informs every forecast.</h2>
            </div>
            <p>Signals become useful only when your team can see where they came from and when they changed.</p>
          </div>

          <ol className="mdx-trace">
            {EVIDENCE_TRACE.map(({ step, label, Icon, items }) => (
              <li key={step}>
                <div className="mdx-trace-label">
                  <b>{step}</b>
                  <Icon size={16} aria-hidden="true" />
                  <h3>{label}</h3>
                </div>
                <div className="mdx-trace-items">
                  {items.map((item) => (
                    <span key={item}>
                      {step === "04" ? <Check size={13} aria-hidden="true" /> : null}
                      {item}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ol>

          <div className="mdx-industry-block">
            <div className="mdx-industry-heading">
              <div>
                <p className="mdx-kicker mdx-kicker-dark">One engine, five operating languages</p>
                <h2>Fluent in the shape of your demand.</h2>
              </div>
              <p>The reasoning stays consistent. The evidence, risk, and decision vocabulary change with the operation.</p>
            </div>

            <div className="mdx-industry-tabs" role="tablist" aria-label="Industry examples">
              {INDUSTRIES.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  role="tab"
                  aria-selected={industry === item.key}
                  aria-controls="industry-reading"
                  className={industry === item.key ? "is-active" : ""}
                  onClick={() => setIndustry(item.key)}
                >
                  <span>{item.number}</span>
                  <strong>{item.label}</strong>
                  <small>{item.observes}</small>
                </button>
              ))}
            </div>

            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                id="industry-reading"
                role="tabpanel"
                className="mdx-industry-reading"
                key={activeIndustry.key}
                initial={reduceMotion ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                <div><span>Sanket observes</span><strong>{activeIndustry.observes}</strong></div>
                <div><span>Emerging risk</span><strong>{activeIndustry.risk}</strong></div>
                <div><span>Recommended response</span><strong>{activeIndustry.action}</strong></div>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </section>

      <section id="pricing" className="mdx-plans" aria-labelledby="plans-title">
        <div className="mdx-shell">
          <div className="mdx-plans-head">
            <div>
              <p className="mdx-kicker">03 / Decision scenarios</p>
              <h2 id="plans-title">Plans you can defend.</h2>
              <p>Same evidence. Different operating priorities. Compare the consequence before choosing the action.</p>
            </div>
            <div className="mdx-plan-status"><span>Demo scenario</span><strong>Same inputs · three policies</strong></div>
          </div>

          <div className="mdx-scenario-table" aria-label="Illustrative operating scenario comparison">
            <div className="mdx-scenario-row mdx-scenario-head" aria-hidden="true">
              <span>Plan</span>
              <span>Service target</span>
              <span>Average inventory</span>
              <span>Stockouts P50</span>
              <span>Working capital</span>
              <span>Reading</span>
            </div>
            {SCENARIOS.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-pressed={scenario === item.key}
                className={`mdx-scenario-row ${scenario === item.key ? "is-active" : ""}`}
                onClick={() => setScenario(item.key)}
              >
                <span data-label="Plan"><strong>{item.name}</strong><small>{item.principle}</small></span>
                <span data-label="Service">{item.service}</span>
                <span data-label="Inventory">{item.inventory}</span>
                <span data-label="Stockouts">{item.stockouts}</span>
                <span data-label="Capital">{item.capital}</span>
                <span data-label="Reading">{item.note}</span>
              </button>
            ))}
          </div>

          <div className="mdx-selected-plan" aria-live="polite">
            <span>Selected policy</span>
            <strong>{activeScenario.name}</strong>
            <p>{activeScenario.note}</p>
            <button type="button" onClick={onSandbox}>Test this decision <ArrowRight size={16} /></button>
          </div>

          <div className="mdx-final">
            <div>
              <p className="mdx-kicker">The Sanket difference</p>
              <h2>From uncertain signals<br />to confident decisions.</h2>
              <p>Sanket does not hide uncertainty. It explains, validates, and turns it into an action your supply-chain team can review.</p>
            </div>
            <div className="mdx-final-principles">
              <div><ScanSearch size={19} /><span><strong>Explainable</strong>Understand why the forecast looks the way it does.</span></div>
              <div><PackageCheck size={19} /><span><strong>Actionable</strong>Review clear quantities, dates, and next steps.</span></div>
            </div>
            <div className="mdx-final-actions">
              <button type="button" onClick={onBook}>Book a demo <ArrowRight size={16} /></button>
              <button type="button" onClick={onSandbox}>Open sandbox</button>
            </div>
          </div>
        </div>
      </section>

      <footer className="mdx-footer">
        <div className="mdx-shell">
          <div className="mdx-footer-top">
            <div className="mdx-footer-brand">
              <LogoMark size={29} variant="bare" curveColor="#BDD9D7" />
              <span>SANKET</span>
              <p>Demand forecasting for supply-chain teams.</p>
            </div>
            <nav aria-label="Footer navigation">
              <a href="#features">Platform</a>
              <a href="#how-it-works">How it works</a>
              <a href="#architecture">Architecture</a>
              <button type="button" onClick={onBook}>Book a demo</button>
              <Link to="/terms">Terms</Link>
              <Link to="/privacy">Privacy</Link>
            </nav>
          </div>
          <div className="mdx-footer-bottom">
            <span>© 2026 Sanket Technologies</span>
            <span>Fashion · Electronics · Pharma · Hardware · Agrocenter</span>
          </div>
        </div>
      </footer>
    </main>
  );
};
