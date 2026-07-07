const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "SANKET Investor Pitch";

// ── Color palette ──────────────────────────────────────────
const C = {
  navyDark:   "0A1628",
  navyMid:    "0D2B44",
  navy:       "0D2137",
  teal:       "0D9488",
  tealBright: "14B8A6",
  tealMid:    "5EEAD4",
  white:      "FFFFFF",
  offWhite:   "F8FAFC",
  slate:      "64748B",
  slateLight: "CBD5E1",
  dark:       "0F172A",
  cardBorder: "E2E8F0",
};

const makeShadow = () => ({
  type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.09,
});

// ============================================================
// SLIDE 1 — Title
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.navyDark };

  s.addShape(pres.shapes.OVAL, {
    x: 7.0, y: -1.6, w: 4.6, h: 4.6,
    fill: { color: C.teal, transparency: 78 },
    line: { color: C.teal, transparency: 78 },
  });
  s.addShape(pres.shapes.OVAL, {
    x: -1.2, y: 3.4, w: 3.2, h: 3.2,
    fill: { color: C.tealBright, transparency: 85 },
    line: { color: C.tealBright, transparency: 85 },
  });

  s.addText("SANKET", {
    x: 0.5, y: 1.05, w: 9.0, h: 1.55,
    fontSize: 80, fontFace: "Arial Black", bold: true,
    color: C.white, align: "center", margin: 0,
  });

  s.addText("AI-Powered Supply Chain Intelligence", {
    x: 0.5, y: 2.72, w: 9.0, h: 0.62,
    fontSize: 21, fontFace: "Trebuchet MS",
    color: C.tealMid, align: "center", margin: 0,
  });

  s.addText("Probabilistic Forecasting  ·  Real-Time Signal Fusion  ·  Multi-Industry SaaS", {
    x: 1.0, y: 3.45, w: 8.0, h: 0.45,
    fontSize: 12, fontFace: "Calibri",
    color: C.slateLight, align: "center", margin: 0,
  });

  s.addText("INVESTOR PRESENTATION  ·  2026", {
    x: 0.5, y: 5.1, w: 9.0, h: 0.35,
    fontSize: 9.5, fontFace: "Calibri", charSpacing: 3,
    color: C.slate, align: "center", margin: 0,
  });
}

// ============================================================
// SLIDE 2 — The Problem
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.offWhite };

  s.addText("Supply Chains Are Flying Blind", {
    x: 0.5, y: 0.28, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.dark, align: "left", margin: 0,
  });

  // Big stat block
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.08, w: 2.9, h: 3.95,
    fill: { color: C.navyDark }, shadow: makeShadow(),
  });
  s.addText("$1.8T", {
    x: 0.5, y: 1.62, w: 2.9, h: 1.12,
    fontSize: 54, fontFace: "Arial Black", bold: true,
    color: C.tealBright, align: "center", margin: 0,
  });
  s.addText("Lost annually to supply chain failures", {
    x: 0.62, y: 2.85, w: 2.66, h: 0.72,
    fontSize: 13, fontFace: "Calibri", bold: true,
    color: C.white, align: "center", margin: 0,
  });
  s.addText("McKinsey Global Institute", {
    x: 0.62, y: 3.65, w: 2.66, h: 0.32,
    fontSize: 10, fontFace: "Calibri", italic: true,
    color: C.slate, align: "center", margin: 0,
  });

  // 3 problem cards
  const problems = [
    {
      num: "01", title: "Demand Blindness",
      body: "Companies forecast from last year's sales — ignoring a viral Reddit thread, a Fed inflation report, or Google Trends data that exists right now.",
    },
    {
      num: "02", title: "Industry Lock-In",
      body: "Most platforms treat all inventory the same. Pharma batches and fashion SKUs have completely different risk profiles, compliance requirements, and demand patterns.",
    },
    {
      num: "03", title: "Reactive, Not Predictive",
      body: "By the time a shortage alert fires, the damage is done. Teams need 30–90 days of forward visibility — not 3 days after a stockout has begun.",
    },
  ];

  problems.forEach((p, i) => {
    const cx = 3.65, cy = 1.08 + i * 1.33, cw = 5.95, ch = 1.2;
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: C.white }, shadow: makeShadow(),
      line: { color: C.cardBorder, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: 0.07, h: ch,
      fill: { color: C.teal }, line: { color: C.teal },
    });
    s.addText(p.num, {
      x: cx + 0.14, y: cy + 0.09, w: 0.52, h: 0.38,
      fontSize: 17, fontFace: "Arial Black", bold: true,
      color: C.teal, align: "center", margin: 0,
    });
    s.addText(p.title, {
      x: cx + 0.74, y: cy + 0.1, w: 4.9, h: 0.36,
      fontSize: 14, fontFace: "Trebuchet MS", bold: true,
      color: C.dark, align: "left", margin: 0,
    });
    s.addText(p.body, {
      x: cx + 0.74, y: cy + 0.49, w: 4.9, h: 0.62,
      fontSize: 10.5, fontFace: "Calibri",
      color: C.slate, align: "left", margin: 0,
    });
  });
}

// ============================================================
// SLIDE 3 — The Solution
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.navy };

  s.addText("Introducing SANKET", {
    x: 0.5, y: 0.28, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.white, align: "left", margin: 0,
  });
  s.addText("Three capabilities that no incumbent platform delivers together", {
    x: 0.5, y: 0.9, w: 9.0, h: 0.35,
    fontSize: 12, fontFace: "Calibri", italic: true,
    color: C.tealMid, align: "left", margin: 0,
  });

  const features = [
    {
      num: "01", title: "Probabilistic Intelligence",
      body: "P10 / P50 / P90 forecast bands per SKU — best case, most likely, worst case. Not a single number, but a calibrated probability distribution that drives smarter procurement decisions.",
      note: "Foundation models + stacked ensemble (TimesFM, Chronos, LightGBM, TFT, DeepAR)",
    },
    {
      num: "02", title: "Real-Time Signal Fusion",
      body: "Every 15 minutes SANKET ingests FRED economic data, Google Trends, and Reddit sentiment — fusing them into the forecast. Demand shifts when CPI spikes or a product goes viral.",
      note: "Signals processed before the next sales report hits your inbox",
    },
    {
      num: "03", title: "Built for 3 Verticals",
      body: "Fashion, Electronics, and Pharma — each with industry-specific ML models, compliance requirements, and optimization engines. One platform, three industries, single deployment.",
      note: "GxP batch compliance  ·  markdown optimization  ·  chip lead-time risk",
    },
  ];

  features.forEach((f, i) => {
    const cx = 0.5 + i * 3.1, cy = 1.35, cw = 2.9, ch = 3.98;
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: C.navyMid }, line: { color: C.teal, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: 0.06,
      fill: { color: C.teal }, line: { color: C.teal },
    });
    s.addShape(pres.shapes.OVAL, {
      x: cx + 0.18, y: cy + 0.18, w: 0.5, h: 0.5,
      fill: { color: C.teal }, line: { color: C.tealBright, width: 0.5 },
    });
    s.addText(f.num, {
      x: cx + 0.18, y: cy + 0.18, w: 0.5, h: 0.5,
      fontSize: 12, fontFace: "Arial Black",
      color: C.white, align: "center", valign: "middle", margin: 0,
    });
    s.addText(f.title, {
      x: cx + 0.15, y: cy + 0.82, w: cw - 0.3, h: 0.52,
      fontSize: 14, fontFace: "Trebuchet MS", bold: true,
      color: C.white, align: "left", margin: 0,
    });
    s.addText(f.body, {
      x: cx + 0.15, y: cy + 1.38, w: cw - 0.3, h: 1.82,
      fontSize: 10.5, fontFace: "Calibri",
      color: C.slateLight, align: "left", margin: 0,
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx + 0.15, y: cy + 3.25, w: cw - 0.3, h: 0.6,
      fill: { color: C.teal, transparency: 83 },
      line: { color: C.teal, transparency: 55 },
    });
    s.addText(f.note, {
      x: cx + 0.2, y: cy + 3.27, w: cw - 0.4, h: 0.56,
      fontSize: 9, fontFace: "Calibri", italic: true,
      color: C.tealMid, align: "left", margin: 0,
    });
  });
}

// ============================================================
// SLIDE 4 — Market Opportunity
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.offWhite };

  s.addText("A Large, Underserved Market", {
    x: 0.5, y: 0.28, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.dark, align: "left", margin: 0,
  });

  const stats = [
    { num: "$28.9B", label: "Global SCM Software Market", sub: "Growing at 11.4% CAGR", bg: C.navyDark },
    { num: "$6.2B",  label: "Demand Planning Segment",   sub: "Projected $10B+ by 2030", bg: C.teal },
    { num: "$2B+",   label: "SANKET Addressable Slice",  sub: "Mid-market + 3 verticals", bg: "0A3D2E" },
  ];

  stats.forEach((st, i) => {
    const bx = 0.5 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x: bx, y: 1.08, w: 2.9, h: 2.15,
      fill: { color: st.bg }, shadow: makeShadow(),
    });
    s.addText(st.num, {
      x: bx + 0.1, y: 1.22, w: 2.7, h: 0.9,
      fontSize: 44, fontFace: "Arial Black", bold: true,
      color: C.tealBright, align: "center", margin: 0,
    });
    s.addText(st.label, {
      x: bx + 0.1, y: 2.17, w: 2.7, h: 0.45,
      fontSize: 11, fontFace: "Calibri", bold: true,
      color: C.white, align: "center", margin: 0,
    });
    s.addText(st.sub, {
      x: bx + 0.1, y: 2.64, w: 2.7, h: 0.32,
      fontSize: 9.5, fontFace: "Calibri", italic: true,
      color: C.tealMid, align: "center", margin: 0,
    });
  });

  // Target customer box
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.42, w: 9.1, h: 1.9,
    fill: { color: C.navyDark }, shadow: makeShadow(),
  });
  s.addText("Who We Serve", {
    x: 0.75, y: 3.55, w: 8.6, h: 0.38,
    fontSize: 13, fontFace: "Trebuchet MS", bold: true,
    color: C.tealBright, align: "left", margin: 0,
  });
  s.addText("Mid-market to enterprise companies ($50M–$5B revenue) who are too big for spreadsheets but too agile for a 3-year SAP implementation. Fashion, Electronics, and Pharma together represent ~40% of global inventory value.", {
    x: 0.75, y: 3.97, w: 8.6, h: 0.55,
    fontSize: 11.5, fontFace: "Calibri",
    color: C.white, align: "left", margin: 0,
  });

  const verts = [
    "Fashion — markdown & sell-through",
    "Electronics — component lead-time risk",
    "Pharma — GxP compliance & shortages",
  ];
  verts.forEach((v, i) => {
    s.addShape(pres.shapes.OVAL, {
      x: 0.75 + i * 3.05, y: 4.67, w: 0.2, h: 0.2,
      fill: { color: C.tealBright }, line: { color: C.tealBright },
    });
    s.addText(v, {
      x: 1.04 + i * 3.05, y: 4.65, w: 2.75, h: 0.28,
      fontSize: 10, fontFace: "Calibri",
      color: C.slateLight, align: "left", margin: 0,
    });
  });
}

// ============================================================
// SLIDE 5 — Platform Features
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.offWhite };

  s.addText("The Platform — What's Inside", {
    x: 0.5, y: 0.28, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.dark, align: "left", margin: 0,
  });

  const feats = [
    { title: "ML Ensemble",            body: "9 model families: TimesFM, Chronos, LightGBM, TFT, DeepAR. Stacked ensemble weights minimize pinball loss for calibrated outputs." },
    { title: "Causal AI",              body: "Promo uplift estimation via DoWhy + EconML. Measure what actually causes demand changes — not just correlations." },
    { title: "Real-Time WebSocket",    body: "Redis pub/sub fan-out. Live forecast progress, shortage alerts, and KPI updates streamed to all connected browsers." },
    { title: "Enterprise Compliance",  body: "PostgreSQL row-level security, GxP batch release, immutable audit logs, HMAC-signed webhooks, and role-based access control." },
    { title: "Cloud-Native Infra",     body: "Docker + Kubernetes, multi-region routing, Prometheus & Grafana observability, CI/CD pipelines, nightly encrypted backups." },
    { title: "Usage-Based Billing",    body: "Stripe metering and subscription tiers with Billing Portal. Usage tracked per API call and per forecast run — natural expansion path." },
  ];

  feats.forEach((f, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const cx = 0.5 + col * 3.1, cy = 1.1 + row * 2.1, cw = 2.9, ch = 1.94;
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: C.white }, shadow: makeShadow(),
      line: { color: C.cardBorder, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: 0.06,
      fill: { color: C.teal }, line: { color: C.teal },
    });
    s.addShape(pres.shapes.OVAL, {
      x: cx + 0.14, y: cy + 0.14, w: 0.42, h: 0.42,
      fill: { color: C.teal }, line: { color: C.teal },
    });
    s.addText((i + 1).toString().padStart(2, "0"), {
      x: cx + 0.14, y: cy + 0.14, w: 0.42, h: 0.42,
      fontSize: 11, fontFace: "Arial Black",
      color: C.white, align: "center", valign: "middle", margin: 0,
    });
    s.addText(f.title, {
      x: cx + 0.66, y: cy + 0.15, w: cw - 0.82, h: 0.4,
      fontSize: 13, fontFace: "Trebuchet MS", bold: true,
      color: C.dark, align: "left", margin: 0,
    });
    s.addText(f.body, {
      x: cx + 0.14, y: cy + 0.66, w: cw - 0.28, h: 1.18,
      fontSize: 10, fontFace: "Calibri",
      color: C.slate, align: "left", margin: 0,
    });
  });
}

// ============================================================
// SLIDE 6 — What We've Built
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.navyDark };

  s.addText("7 Phases. ~230 Files. Production-Ready.", {
    x: 0.5, y: 0.25, w: 9.0, h: 0.65,
    fontSize: 28, fontFace: "Arial Black", bold: true,
    color: C.white, align: "left", margin: 0,
  });
  s.addText("Not a mockup. Every component is written, tested, and containerized.", {
    x: 0.5, y: 0.88, w: 9.0, h: 0.35,
    fontSize: 12, fontFace: "Calibri", italic: true,
    color: C.tealMid, align: "left", margin: 0,
  });

  const phases = [
    { ph: "01", label: "Backend API",       detail: "FastAPI + PostgreSQL RLS, JWT auth, multi-tenant, GxP" },
    { ph: "02", label: "ML Stack",          detail: "9 model families, stacked ensemble, causal AI, OR-Tools" },
    { ph: "03", label: "Frontend",          detail: "React + TS dashboard, industry switcher, real-time charts" },
    { ph: "04", label: "Infrastructure",    detail: "K8s, Prometheus/Grafana, CI/CD, migrations, backups" },
    { ph: "05", label: "Realtime + Billing",detail: "WebSocket pub/sub, Stripe metering, webhooks, multi-region" },
    { ph: "06", label: "Trend Fusion",      detail: "FRED + Trends + Reddit fused into hybrid forecasts and alerts" },
    { ph: "07", label: "Connectivity",      detail: "Postgres + real ML service wired end-to-end in docker-compose" },
  ];

  // 7 evenly spaced dots: first center at 0.75, last at 9.25, span = 8.5
  const dotSpan = 8.5;
  const dotStep = dotSpan / 6;
  const dotCenterBase = 0.75;
  const dotR = 0.22;
  const dotY = 1.58;
  const cardW = dotStep - 0.08;
  const cardY = 2.1;
  const cardH = 3.18;

  // Timeline line
  s.addShape(pres.shapes.LINE, {
    x: dotCenterBase, y: dotY + dotR, w: dotSpan, h: 0,
    line: { color: C.teal, width: 1.0 },
  });

  phases.forEach((ph, i) => {
    const cx = dotCenterBase + i * dotStep;
    s.addShape(pres.shapes.OVAL, {
      x: cx - dotR, y: dotY, w: dotR * 2, h: dotR * 2,
      fill: { color: C.teal }, line: { color: C.tealBright, width: 0.5 },
    });
    s.addText(ph.ph, {
      x: cx - dotR, y: dotY, w: dotR * 2, h: dotR * 2,
      fontSize: 9.5, fontFace: "Arial Black",
      color: C.white, align: "center", valign: "middle", margin: 0,
    });

    const cardX = cx - cardW / 2;
    s.addShape(pres.shapes.RECTANGLE, {
      x: cardX, y: cardY, w: cardW, h: cardH,
      fill: { color: C.navyMid }, line: { color: C.teal, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cardX, y: cardY, w: cardW, h: 0.05,
      fill: { color: C.teal }, line: { color: C.teal },
    });
    s.addText(ph.label, {
      x: cardX + 0.06, y: cardY + 0.1, w: cardW - 0.12, h: 0.48,
      fontSize: 9, fontFace: "Trebuchet MS", bold: true,
      color: C.tealBright, align: "center", margin: 0,
    });
    s.addText(ph.detail, {
      x: cardX + 0.06, y: cardY + 0.66, w: cardW - 0.12, h: 2.38,
      fontSize: 8.5, fontFace: "Calibri",
      color: C.slateLight, align: "center", margin: 0,
    });
  });
}

// ============================================================
// SLIDE 7 — Business Model
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.offWhite };

  s.addText("Business Model", {
    x: 0.5, y: 0.25, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.dark, align: "left", margin: 0,
  });
  s.addText("Usage-based SaaS  ·  High gross margin  ·  Natural expansion path", {
    x: 0.5, y: 0.87, w: 9.0, h: 0.35,
    fontSize: 12, fontFace: "Calibri",
    color: C.slate, align: "left", margin: 0,
  });

  const tiers = [
    {
      name: "Starter",    price: "$2,500",  period: "/ month", hl: false, badge: null,
      features: ["1 industry vertical", "Up to 5,000 SKUs", "Probabilistic P10/P50/P90", "Historical ML models", "REST API access"],
    },
    {
      name: "Growth",     price: "$8,000",  period: "/ month", hl: true,  badge: "MOST POPULAR",
      features: ["2 industry verticals", "Up to 50,000 SKUs", "Real-time signal fusion", "Shortage alerts", "WebSocket live updates", "Priority support"],
    },
    {
      name: "Enterprise", price: "Custom",  period: "pricing", hl: false, badge: null,
      features: ["All 3 industries", "Unlimited SKUs", "Multi-region deployment", "GxP pharma compliance", "Dedicated SLA", "Custom ERP integrations"],
    },
  ];

  tiers.forEach((t, i) => {
    const cx = 0.5 + i * 3.1, cy = 1.32, cw = 2.9, ch = 3.78;
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: t.hl ? C.navyDark : C.white },
      shadow: makeShadow(),
      line: t.hl ? { color: C.tealBright, width: 1.5 } : { color: C.cardBorder, width: 0.5 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: 0.06,
      fill: { color: t.hl ? C.tealBright : C.teal },
      line: { color: t.hl ? C.tealBright : C.teal },
    });

    let yOff = cy + 0.18;

    if (t.badge) {
      s.addText(t.badge, {
        x: cx + 0.15, y: yOff, w: cw - 0.3, h: 0.26,
        fontSize: 7.5, fontFace: "Calibri", bold: true, charSpacing: 1.5,
        color: C.tealBright, align: "center", margin: 0,
      });
      yOff += 0.30;
    }

    s.addText(t.name, {
      x: cx + 0.18, y: yOff, w: cw - 0.36, h: 0.42,
      fontSize: 17, fontFace: "Arial Black", bold: true,
      color: t.hl ? C.white : C.dark, align: "left", margin: 0,
    });
    yOff += 0.46;

    s.addText(t.price, {
      x: cx + 0.18, y: yOff, w: cw - 0.36, h: 0.6,
      fontSize: 32, fontFace: "Arial Black", bold: true,
      color: C.tealBright, align: "left", margin: 0,
    });
    yOff += 0.62;

    s.addText(t.period, {
      x: cx + 0.18, y: yOff, w: cw - 0.36, h: 0.28,
      fontSize: 10, fontFace: "Calibri",
      color: t.hl ? C.tealMid : C.slate, align: "left", margin: 0,
    });
    yOff += 0.36;

    s.addShape(pres.shapes.LINE, {
      x: cx + 0.18, y: yOff, w: cw - 0.36, h: 0,
      line: { color: t.hl ? "1E3A4A" : C.cardBorder, width: 0.5 },
    });
    yOff += 0.16;

    t.features.forEach((f) => {
      s.addText("✓  " + f, {
        x: cx + 0.18, y: yOff, w: cw - 0.36, h: 0.27,
        fontSize: 10, fontFace: "Calibri",
        color: t.hl ? C.slateLight : C.slate, align: "left", margin: 0,
      });
      yOff += 0.27;
    });
  });

  // Key metrics row
  const metrics = [
    { val: "85%+",    label: "Gross Margin" },
    { val: "110%+",   label: "Net Revenue Retention" },
    { val: "<12 mo",  label: "Payback Period (Growth)" },
  ];
  metrics.forEach((m, i) => {
    const mx = 0.5 + i * 3.1;
    s.addText(m.val, {
      x: mx, y: 5.2, w: 1.2, h: 0.3,
      fontSize: 15, fontFace: "Arial Black", bold: true,
      color: C.teal, align: "left", margin: 0,
    });
    s.addText(m.label, {
      x: mx + 1.24, y: 5.23, w: 1.7, h: 0.26,
      fontSize: 10, fontFace: "Calibri",
      color: C.slate, align: "left", margin: 0,
    });
  });
}

// ============================================================
// SLIDE 8 — Competitive Advantage
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.offWhite };

  s.addText("Why SANKET Wins", {
    x: 0.5, y: 0.25, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.dark, align: "left", margin: 0,
  });

  const headers = ["Capability", "SANKET", "SAP IBP", "Kinaxis", "Anaplan"];
  const colW = [3.0, 1.5, 1.5, 1.5, 1.5];

  const rows = [
    ["Real-time signal fusion",          "YES", "NO",      "NO",      "NO"],
    ["Probabilistic P10 / P50 / P90",    "YES", "Partial", "Partial", "NO"],
    ["Foundation model forecasting",     "YES", "NO",      "NO",      "NO"],
    ["Multi-industry (3 verticals)",     "YES", "Complex", "NO",      "NO"],
    ["GxP pharma compliance",            "YES", "Costly",  "NO",      "NO"],
    ["Time to deploy",                   "Weeks", "12–18 mo", "6–12 mo", "3–6 mo"],
  ];

  const tableData = [
    headers.map((h, hi) => ({
      text: h,
      options: {
        fill: { color: C.navyDark },
        color: hi === 1 ? C.tealBright : C.white,
        bold: true, fontSize: 10.5,
        align: hi === 0 ? "left" : "center",
      },
    })),
  ];

  rows.forEach((r, ri) => {
    tableData.push(
      r.map((cell, ci) => {
        const isSanket = ci === 1;
        const isYes = cell === "YES";
        const isNo = cell === "NO";
        const rowBg = ri % 2 === 0 ? C.white : "F1F5F9";
        return {
          text: isYes ? "✓" : isNo ? "✗" : cell,
          options: {
            fill: { color: isSanket && isYes ? "E0FDF4" : rowBg },
            color: isSanket && isYes ? C.teal : isNo ? "94A3B8" : isSanket ? "0A6B5E" : C.dark,
            bold: isSanket && isYes,
            fontSize: 10,
            align: ci === 0 ? "left" : "center",
          },
        };
      })
    );
  });

  s.addTable(tableData, {
    x: 0.5, y: 1.0, w: 9.0, h: 3.88,
    colW, rowH: 0.51,
    border: { pt: 0.5, color: C.cardBorder },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.05, w: 9.0, h: 0.4,
    fill: { color: C.navyDark }, line: { color: C.navyDark },
  });
  s.addText("Moat: signal fusion speed + industry compliance depth. Incumbents are too large to pivot. New AI startups lack the GxP regulatory layer.", {
    x: 0.68, y: 5.1, w: 8.7, h: 0.3,
    fontSize: 10, fontFace: "Calibri", italic: true,
    color: C.tealMid, align: "left", margin: 0,
  });
}

// ============================================================
// SLIDE 9 — The Ask
// ============================================================
{
  const s = pres.addSlide();
  s.background = { color: C.navyDark };

  s.addShape(pres.shapes.OVAL, {
    x: 6.7, y: -1.3, w: 4.8, h: 4.8,
    fill: { color: C.teal, transparency: 82 },
    line: { color: C.teal, transparency: 82 },
  });
  s.addShape(pres.shapes.OVAL, {
    x: -1.3, y: 3.1, w: 3.4, h: 3.4,
    fill: { color: C.tealBright, transparency: 88 },
    line: { color: C.tealBright, transparency: 88 },
  });

  s.addText("The Ask", {
    x: 0.5, y: 0.25, w: 9.0, h: 0.62,
    fontSize: 29, fontFace: "Arial Black", bold: true,
    color: C.white, align: "left", margin: 0,
  });

  // Funding box
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.05, w: 3.65, h: 1.65,
    fill: { color: C.navyMid }, line: { color: C.teal, width: 1.0 },
  });
  s.addText("Raising", {
    x: 0.6, y: 1.15, w: 3.45, h: 0.32,
    fontSize: 12, fontFace: "Calibri",
    color: C.tealMid, align: "center", margin: 0,
  });
  s.addText("[Seed / Series A]", {
    x: 0.6, y: 1.48, w: 3.45, h: 0.7,
    fontSize: 24, fontFace: "Arial Black", bold: true,
    color: C.white, align: "center", margin: 0,
  });

  // Use of funds
  s.addText("Use of Funds", {
    x: 4.5, y: 1.05, w: 5.1, h: 0.38,
    fontSize: 14, fontFace: "Trebuchet MS", bold: true,
    color: C.tealBright, align: "left", margin: 0,
  });

  const uses = [
    { num: "01", text: "Go to market — 2 industry sales reps (Fashion + Pharma first, highest ACV)" },
    { num: "02", text: "Close anchor customers — 3 paid pilots currently in discussion" },
    { num: "03", text: "Deepen ML — fine-tune foundation models on customer data (10–20% accuracy lift)" },
    { num: "04", text: "ERP integrations — SAP + NetSuite connectors to accelerate time-to-value" },
  ];

  uses.forEach((u, i) => {
    const uy = 1.55 + i * 0.72;
    s.addShape(pres.shapes.OVAL, {
      x: 4.5, y: uy, w: 0.38, h: 0.38,
      fill: { color: C.teal }, line: { color: C.teal },
    });
    s.addText(u.num, {
      x: 4.5, y: uy, w: 0.38, h: 0.38,
      fontSize: 9.5, fontFace: "Arial Black",
      color: C.white, align: "center", valign: "middle", margin: 0,
    });
    s.addText(u.text, {
      x: 5.0, y: uy + 0.02, w: 4.6, h: 0.38,
      fontSize: 10.5, fontFace: "Calibri",
      color: C.slateLight, align: "left", margin: 0,
    });
  });

  // Closing quote
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.35, w: 9.1, h: 1.0,
    fill: { color: C.navyMid }, line: { color: C.teal, width: 0.5 },
  });
  s.addText(
    "“The companies that win the next decade respond to the market before it moves. SANKET is the platform that makes that possible — for any industry, deployed in weeks, not years.”",
    {
      x: 0.7, y: 4.42, w: 8.7, h: 0.86,
      fontSize: 11.5, fontFace: "Calibri", italic: true,
      color: C.white, align: "center", margin: 0,
    }
  );
}

// ── Write file ──────────────────────────────────────────────
pres
  .writeFile({ fileName: "./SANKET_Investor_Pitch.pptx" })
  .then(() => console.log("SUCCESS: SANKET_Investor_Pitch.pptx written"))
  .catch((err) => { console.error("ERROR:", err); process.exit(1); });
