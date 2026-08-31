import type { IndustryCode } from "@/types/api";

/**
 * Every claim the landing page makes, in one file.
 *
 * The rule for this file is that a reader can check any line against the
 * codebase. Where a value mirrors backend data, the comment names the file it
 * came from. Nothing here is aspirational: no customer names, no revenue
 * figures, no analyst awards, no outcomes we have not measured.
 */

export type Availability = "live" | "beta" | "planned";

/** Mirrors backend/app/services/industry_context.py. */
export const INDUSTRY_DETAIL: Record<
  IndustryCode,
  {
    label: string;
    /** Lives in public/assets/. */
    image: string;
    imageAlt: string;
    horizonWeeks: number;
    auditLevel: string;
    signals: string[];
    observes: string;
    risk: string;
    action: string;
  }
> = {
  fashion: {
    label: "Apparel & Fashion",
    image: "fashion.png",
    imageAlt: "Apparel arranged for inventory and demand planning",
    horizonWeeks: 26,
    auditLevel: "standard",
    signals: ["Search trends", "Social sentiment", "Weather"],
    observes: "SKU · size curve · returns · promotion cadence",
    risk: "A regional search spike precedes store sales.",
    action: "Rebalance by size before replenishing the whole line.",
  },
  electronics: {
    label: "Consumer Electronics",
    image: "electronics.png",
    imageAlt: "Consumer electronics displayed for channel inventory planning",
    horizonWeeks: 12,
    auditLevel: "standard",
    signals: ["Competitor price", "Supplier lead time", "Search trends"],
    observes: "SKU · launch cycle · channel · price movement",
    risk: "A price move shifts demand before channel reports settle.",
    action: "Advance the order window without overcommitting stock.",
  },
  pharma: {
    label: "Pharmaceuticals",
    image: "pharma.png",
    imageAlt: "Pharmaceutical products prepared for traceable supply planning",
    horizonWeeks: 52,
    auditLevel: "gxp",
    signals: ["Regulatory", "Supplier lead time", "Logistics disruption"],
    observes: "SKU · batch · shelf life · regulatory status",
    risk: "A supplier delay threatens cover before expiry windows close.",
    action: "Re-plan the batch with the audit trail attached.",
  },
  agrocenter: {
    label: "Agrocenter & Farm Inputs",
    image: "agro.png",
    imageAlt: "Agricultural supplies prepared for seasonal regional planning",
    horizonWeeks: 26,
    auditLevel: "standard",
    signals: ["Weather", "Macro-economic", "Search trends"],
    observes: "SKU · season · crop cycle · input coverage",
    risk: "A weather shift moves the sowing window and the demand with it.",
    action: "Pull the replenishment forward for the affected inputs.",
  },
  hardware: {
    label: "Hardware & Industrial Supply",
    image: "hardware.png",
    imageAlt: "Hardware products arranged for branch inventory planning",
    horizonWeeks: 16,
    auditLevel: "standard",
    signals: ["Supplier lead time", "Competitor price", "Macro-economic"],
    observes: "SKU · project cycle · branch · supplier lead time",
    risk: "A lead-time slip puts safety stock below cover.",
    action: "Reorder early on the lines that actually move.",
  },
};

/** Routes that exist in frontend/src/App.tsx. */
export const MODULES = [
  {
    key: "forecasts",
    name: "Demand forecasting",
    route: "/workspace/forecasts",
    blurb: "Per-SKU forecasts with confidence bands.",
    detail:
      "Every SKU gets its own model selection rather than one global model. Forecasts carry a confidence interval, so you can see where the engine is unsure instead of reading a single line and hoping.",
  },
  {
    key: "decisions",
    name: "Decision engine",
    route: "/workspace/decisions",
    blurb: "Ranked actions, each with its evidence.",
    detail:
      "Turns the forecast into a reorder you can approve, showing the inputs behind it — days of cover, lead time, protection window — so the recommendation can be argued with.",
  },
  {
    key: "scenarios",
    name: "What-if scenarios",
    route: "/workspace/scenarios",
    blurb: "Change an assumption, see the plan move.",
    detail:
      "Simulate a promotion, a lead-time slip or a price change and compare the resulting plan against the baseline before committing to it.",
  },
  {
    key: "inventory",
    name: "Inventory & cover",
    route: "/workspace/inventory",
    blurb: "Stock positions and days of cover.",
    detail:
      "Current levels by location set against forecast demand, so cover is a number everyone can see rather than an argument between functions.",
  },
  {
    key: "alerts",
    name: "Shortage alerts",
    route: "/workspace/alerts",
    blurb: "Risk scored before it becomes a stockout.",
    detail:
      "Alerts fire on projected cover rather than on hitting zero, and carry the drivers that produced the risk score.",
  },
  {
    key: "accuracy",
    name: "Forecast accuracy",
    route: "/workspace/forecast-accuracy",
    blurb: "Scored against what actually happened.",
    detail:
      "Backtested accuracy per SKU, so you can see where the engine has earned trust and where it has not. A forecast you cannot audit is a guess with a chart.",
  },
  {
    key: "data-quality",
    name: "Data quality",
    route: "/workspace/data-quality",
    blurb: "What is missing, before it skews a plan.",
    detail:
      "Flags gaps, duplicates and outliers in ingested data rather than silently forecasting on top of them.",
  },
  {
    key: "roi",
    name: "ROI dashboard",
    route: "/workspace/roi",
    blurb: "Value traced back to decisions taken.",
    detail:
      "Ties working-capital and stockout impact to the specific recommendations that were approved, so the platform's value is measured rather than asserted.",
  },
  {
    key: "signals",
    name: "External signals",
    route: "/workspace/signals",
    blurb: "Weather, trends, macro and competitor movement.",
    detail:
      "Signals are ingested, validated and attached to the SKUs they plausibly affect, so a forecast change has a named cause.",
  },
  {
    key: "integrations",
    name: "Integrations hub",
    route: "/workspace/integrations",
    blurb: "Connect a storefront, warehouse or database.",
    detail:
      "Connect a source or upload a file; SANKET maps it into the canonical schema without a migration project.",
  },
] as const;

/** Mirrors the SignalType enum in backend/app/models/enums.py. */
export const SIGNALS = [
  {
    key: "weather",
    name: "Weather",
    source: "Open-Meteo",
    feeds: "Seasonal demand, sowing windows and footfall.",
  },
  {
    key: "trend_search",
    name: "Search trends",
    source: "Google Trends",
    feeds: "Demand movement that shows up online before it reaches your sales.",
  },
  {
    key: "social_sentiment",
    name: "Social sentiment",
    source: "Reddit",
    feeds: "Category interest and emerging product conversation.",
  },
  {
    key: "competitor_price",
    name: "Competitor price",
    source: "Retail price tracking",
    feeds: "Share shift when a rival moves on price.",
  },
  {
    key: "macro_economic",
    name: "Macro-economic",
    source: "FRED",
    feeds: "Demand pressure from rates, inflation and industrial output.",
  },
  {
    key: "regulatory",
    name: "Regulatory",
    source: "FDA feeds",
    feeds: "Supply risk from recalls and approval changes.",
  },
  {
    key: "supplier_lead",
    name: "Supplier lead time",
    source: "Connected ERP and purchase orders",
    feeds: "The protection window, and therefore reorder timing.",
  },
  {
    key: "logistics_disruption",
    name: "Logistics disruption",
    source: "Freight and port feeds",
    feeds: "Delay risk on inbound stock.",
  },
] as const;

/**
 * Mirrors backend/app/connectors/catalog.py — the source of truth.
 *
 * A static copy because the real catalog is served by an authenticated endpoint
 * and this page is public. It can drift when providers are added; check it
 * against the backend file when you touch either.
 *
 * `availability` is load-bearing, not decoration. Six of these work today. The
 * page previously advertised "29+ CONNECTORS" by counting the planned ones,
 * which is the kind of claim this file exists to prevent.
 */
export const CONNECTORS: { name: string; category: string; availability: Availability }[] = [
  { name: "Shopify", category: "Sales & E-commerce", availability: "live" },
  { name: "WooCommerce", category: "Sales & E-commerce", availability: "live" },
  { name: "CSV Upload", category: "Files", availability: "live" },
  { name: "Excel Upload", category: "Files", availability: "live" },
  { name: "PostgreSQL", category: "Databases", availability: "live" },
  { name: "MySQL", category: "Databases", availability: "live" },
  { name: "REST API / Push", category: "API", availability: "beta" },
  { name: "Generic Webhooks", category: "Streaming", availability: "beta" },
  { name: "Magento", category: "Sales & E-commerce", availability: "planned" },
  { name: "BigCommerce", category: "Sales & E-commerce", availability: "planned" },
  { name: "Amazon Seller", category: "Sales & E-commerce", availability: "planned" },
  { name: "Flipkart Seller", category: "Sales & E-commerce", availability: "planned" },
  { name: "Square", category: "Point of Sale", availability: "planned" },
  { name: "Lightspeed", category: "Point of Sale", availability: "planned" },
  { name: "Toast", category: "Point of Sale", availability: "planned" },
  { name: "Clover", category: "Point of Sale", availability: "planned" },
  { name: "SAP S/4HANA", category: "ERP & Inventory", availability: "planned" },
  { name: "Oracle ERP", category: "ERP & Inventory", availability: "planned" },
  { name: "Microsoft Dynamics 365", category: "ERP & Inventory", availability: "planned" },
  { name: "Oracle NetSuite", category: "ERP & Inventory", availability: "planned" },
  { name: "Odoo", category: "ERP & Inventory", availability: "planned" },
  { name: "Tally Prime / ERP 9", category: "ERP & Inventory", availability: "planned" },
  { name: "Zoho Books", category: "ERP & Inventory", availability: "planned" },
  { name: "Zoho Inventory", category: "ERP & Inventory", availability: "planned" },
  { name: "Busy Accounting", category: "ERP & Inventory", availability: "planned" },
  { name: "Marg ERP", category: "ERP & Inventory", availability: "planned" },
  { name: "Vyapar", category: "ERP & Inventory", availability: "planned" },
  { name: "ERPNext / Frappe", category: "ERP & Inventory", availability: "planned" },
  { name: "Unicommerce", category: "ERP & Inventory", availability: "planned" },
  { name: "Manhattan Associates", category: "Warehouse", availability: "planned" },
  { name: "Blue Yonder", category: "Warehouse", availability: "planned" },
  { name: "Infor WMS", category: "Warehouse", availability: "planned" },
  { name: "Fishbowl", category: "Warehouse", availability: "planned" },
  { name: "Snowflake", category: "Data Warehouse", availability: "planned" },
  { name: "Databricks", category: "Data Warehouse", availability: "planned" },
  { name: "Google BigQuery", category: "Data Warehouse", availability: "planned" },
  { name: "Amazon Redshift", category: "Data Warehouse", availability: "planned" },
  { name: "Azure Synapse", category: "Data Warehouse", availability: "planned" },
  { name: "Apache Kafka", category: "Streaming", availability: "planned" },
  { name: "RabbitMQ", category: "Streaming", availability: "planned" },
  { name: "AWS Kinesis", category: "Streaming", availability: "planned" },
  { name: "Google Pub/Sub", category: "Streaming", availability: "planned" },
];

export const CONNECTOR_CATEGORIES = [...new Set(CONNECTORS.map((c) => c.category))];
export const TOTAL_CONNECTOR_COUNT = CONNECTORS.length;
export const LIVE_CONNECTOR_COUNT = CONNECTORS.filter((c) => c.availability === "live").length;
