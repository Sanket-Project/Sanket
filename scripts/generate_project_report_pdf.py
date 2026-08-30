import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

# ----------------------------------------------------------------------
# NumberedCanvas for Page X of Y footers and header banners
# ----------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_header_footer(self, page_count):
        self.saveState()
        
        # Suppress header and footer on cover / title page (Page 1)
        if self._pageNumber > 1:
            # Header
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#475569"))
            self.drawString(36, 756, "SANKET — Enterprise Multi-Industry Predictive Analytics & Supply Chain SaaS")
            self.setFont("Helvetica", 8)
            self.drawRightString(576, 756, "Technical & Project Audit Report")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 750, 576, 750)

            # Footer
            self.line(36, 45, 576, 45)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(36, 32, "CONFIDENTIAL & PROPRIETARY — SANKET PLATFORM")
            page_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(576, 32, page_text)
            
        self.restoreState()


def build_pdf(filename="SANKET_Comprehensive_Project_Report.pdf"):
    # Ensure target directory exists if specified
    out_dir = os.path.dirname(filename)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Color palette
    PRIMARY = colors.HexColor("#0F172A")    # Slate 900
    SECONDARY = colors.HexColor("#1E3A8A")  # Blue 900
    ACCENT = colors.HexColor("#0284C7")     # Sky 600
    TEXT_DARK = colors.HexColor("#1E293B")  # Slate 800
    BG_LIGHT = colors.HexColor("#F8FAFC")   # Slate 50
    BORDER_COLOR = colors.HexColor("#E2E8F0")

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=PRIMARY,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=ACCENT,
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=SECONDARY,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_DARK,
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_DARK,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=4
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=TEXT_DARK
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.white
    )

    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=0
    )

    meta_callout_style = ParagraphStyle(
        'MetaCallout',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155")
    )

    story = []

    # ----------------------------------------------------------------------
    # TITLE BLOCK & METADATA
    # ----------------------------------------------------------------------
    story.append(Paragraph("SANKET Platform — Comprehensive Project & Technical Report", title_style))
    story.append(Paragraph("Enterprise Multi-Industry Predictive Analytics & Supply Chain SaaS", subtitle_style))
    
    meta_table_data = [
        [
            Paragraph("<b>Repository:</b> Sanket-Project / Prisma", table_cell_style),
            Paragraph("<b>Audit Date:</b> July 2026", table_cell_style),
            Paragraph("<b>Status:</b> Advanced MVP / Operational Beta", table_cell_style)
        ],
        [
            Paragraph("<b>Backend Stack:</b> FastAPI, Python 3.12, PostgreSQL 16 + RLS", table_cell_style),
            Paragraph("<b>ML Engine:</b> PyTorch, Chronos T5, LightGBM, OR-Tools", table_cell_style),
            Paragraph("<b>Frontend:</b> React 18, Vite 5, TypeScript 5.6", table_cell_style)
        ]
    ]
    meta_table = Table(meta_table_data, colWidths=[180, 180, 180])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # TABLE OF CONTENTS
    # ----------------------------------------------------------------------
    story.append(Paragraph("Table of Contents", h2_style))
    toc_data = [
        [Paragraph("<b>1. PROJECT OVERVIEW</b>", table_cell_style), Paragraph("Platform Identity, Value Proposition, Target Verticals & Operational Stage", table_cell_style)],
        [Paragraph("<b>2. FEATURES</b>", table_cell_style), Paragraph("Core System Capabilities, Specialized Features & In-Progress Roadmap Items", table_cell_style)],
        [Paragraph("<b>3. MODELS</b>", table_cell_style), Paragraph("ML/AI Forecasting Stack, Causal Engine, Optimization & Database Entities", table_cell_style)],
        [Paragraph("<b>4. FUNCTIONS & FUNCTIONALITIES</b>", table_cell_style), Paragraph("Core Backend Services, API Routers, ML Engine Modules & Connectors", table_cell_style)],
        [Paragraph("<b>5. USES</b>", table_cell_style), Paragraph("Realistic Industry Workflows & End-to-End Operational Scenarios", table_cell_style)],
        [Paragraph("<b>6. ARCHITECTURE</b>", table_cell_style), Paragraph("Full Tech Stack, Data Flow Pipelines, DevOps & Design Tradeoffs", table_cell_style)],
        [Paragraph("<b>7. COMPLETE PROJECT VIEW</b>", table_cell_style), Paragraph("Holistic Synthesis, Known Limitations & Immediate Strategic Next Steps", table_cell_style)],
    ]
    toc_table = Table(toc_data, colWidths=[150, 390])
    toc_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(toc_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceBefore=2, spaceAfter=8))

    # ----------------------------------------------------------------------
    # 1. PROJECT OVERVIEW
    # ----------------------------------------------------------------------
    story.append(Paragraph("1. PROJECT OVERVIEW", h1_style))
    
    story.append(Paragraph("Platform Identity & Problem Solved", h2_style))
    story.append(Paragraph(
        "<b>SANKET</b> (referenced in codebase manifests as <i>Prisma / Sanket-Project</i>) is a vertically integrated, multi-tenant SaaS platform delivering enterprise predictive analytics, demand forecasting, causal inference, and supply chain optimization. Enterprise supply chains struggle with extreme demand volatility, multi-echelon stockouts, costly overstocking capital drag, supplier lead-time variance, and stringent regulatory audit burdens. SANKET solves these challenges by combining advanced machine learning forecasters (foundation models, deep learning, gradient boosting, and statistical models) with mathematical supply-chain optimization, robust PostgreSQL row-level security (RLS), and industry-specific contextual profiles.",
        body_style
    ))

    story.append(Paragraph("Target Users & Industry Verticals", h2_style))
    story.append(Paragraph(
        "The platform is specifically built for supply chain directors, demand planners, inventory managers, QA managers, and financial analysts across five target industry verticals:",
        body_style
    ))

    verticals_data = [
        [Paragraph("<b>Industry Vertical</b>", table_header_style), Paragraph("<b>Supply Chain Focus & Platform Solution</b>", table_header_style), Paragraph("<b>Compliance Level</b>", table_header_style)],
        [
            Paragraph("<b>Apparel & Fashion</b>", table_cell_style),
            Paragraph("Short product lifecycles, high seasonality, style/color/size SKU complexity. Solved via seasonal decomposition, Google Trends signals, and markdown optimization.", table_cell_style),
            Paragraph("Standard", table_cell_style)
        ],
        [
            Paragraph("<b>Consumer Electronics</b>", table_cell_style),
            Paragraph("Rapid product obsolescence, complex multi-tier BOMs, component lead-time volatility. Solved via component lead-time forecasting and automated shortage alerts.", table_cell_style),
            Paragraph("Standard", table_cell_style)
        ],
        [
            Paragraph("<b>Pharmaceuticals</b>", table_cell_style),
            Paragraph("Strict regulatory compliance, lot expiration risks, cold-chain temperature thresholds (-20°C to +8°C). Solved via FDA signal ingestion, batch quarantine/release, and immutable audit logs.", table_cell_style),
            Paragraph("<b>GxP / 21 CFR Part 11</b>", table_cell_style)
        ],
        [
            Paragraph("<b>Agriculture (Agrocenter)</b>", table_cell_style),
            Paragraph("Perishable goods shelf-life, crop yield volatility, macro weather dependencies. Solved via real-time Open-Meteo weather connectors and regional demand modeling.", table_cell_style),
            Paragraph("Standard", table_cell_style)
        ],
        [
            Paragraph("<b>Hardware</b>", table_cell_style),
            Paragraph("Project-based procurement, milestone-based delivery, long-lead supplier components. Solved via project BOM tracking and lead-time forecast modeling.", table_cell_style),
            Paragraph("Standard", table_cell_style)
        ]
    ]
    v_table = Table(verticals_data, colWidths=[110, 330, 100])
    v_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT])
    ]))
    story.append(v_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Current Project Stage", h2_style))
    story.append(Paragraph(
        "Based on direct codebase observation, SANKET is in an <b>Advanced MVP / Operational Beta</b> stage. The database layer (31+ tables, RLS enforcement, pgvector HNSW indexing, range partitioning), FastAPI backend, PyTorch ML engine, and React/Vite dashboard are fully functional. Recent core enhancements (July 2026) verified and resolved subscription entitlement guards (returning HTTP 402 for unsubscribed tenants) and workspace context token re-minting.",
        body_style
    ))

    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # 2. FEATURES
    # ----------------------------------------------------------------------
    story.append(Paragraph("2. FEATURES", h1_style))
    
    story.append(Paragraph("Core System Capabilities", h2_style))
    story.append(Paragraph("• <b>PostgreSQL Row-Level Security (RLS):</b> Mandatory tenant isolation enforced at the DB kernel level via <code>app.current_tenant_id</code> and <code>FORCE ROW LEVEL SECURITY</code> on all tenant-scoped tables.", bullet_style))
    story.append(Paragraph("• <b>Multi-Vertical Workspace Switching:</b> Dynamic switching between Fashion, Electronics, Pharma, Agro, and Hardware via <code>X-Industry-Code</code> request header and validated JWT claims.", bullet_style))
    story.append(Paragraph("• <b>5-Stage Ensembled ML Forecasting:</b> Full pipeline: historical sales loading, intermittency classification, model pre-training, domain fitting, SLSQP convex ensemble optimization, and backtest reporting.", bullet_style))
    story.append(Paragraph("• <b>Zero-Shot Chronos Fallback:</b> Instant zero-shot demand forecasting via Amazon Chronos T5 (<code>amazon/chronos-t5-small</code>) when trained model artifacts are absent.", bullet_style))
    story.append(Paragraph("• <b>Pharma GxP & 21 CFR Part 11 Compliance:</b> Immutable audit logging (updates and deletes blocked by PostgreSQL SQL rules), batch lot quarantine/release tracking, cold-chain temperature validation, and QA signatures.", bullet_style))
    story.append(Paragraph("• <b>Supply Chain Optimization Suite:</b> Automated Safety Stock calculation, Economic Order Quantity (EOQ), Markdown pricing optimization, Multi-Echelon replenishment, and Reinforcement Learning (RL) replenishment.", bullet_style))
    story.append(Paragraph("• <b>External Signal Ingestion & Vector Clustering:</b> Real-time connectors for Weather (Open-Meteo), FRED macroeconomics, Google Trends, Reddit sentiment, Competitor prices, FDA regulatory notices, and 768-dim pgvector HNSW clustering.", bullet_style))

    story.append(Paragraph("Secondary & Specialized Features", h2_style))
    story.append(Paragraph("• <b>Real-Time WebSockets:</b> Live sales streaming server (<code>websocket.py</code>) pushing notifications to connected client sessions.", bullet_style))
    story.append(Paragraph("• <b>Multi-Format Data Importer:</b> Async parsing and chunked DB insertion of CSV and Excel (<code>.xlsx</code>) sales data with schema validation.", bullet_style))
    story.append(Paragraph("• <b>E-Commerce Sync Connectors:</b> Direct pollers and sync handlers for Shopify REST/GraphQL and WooCommerce endpoints.", bullet_style))
    story.append(Paragraph("• <b>Direct SQL Data Connector:</b> Direct integration capabilities for external MySQL and PostgreSQL source databases.", bullet_style))
    story.append(Paragraph("• <b>Financial & What-If Scenario Analysis:</b> Simulation engines evaluating revenue exposure, margin impact, and stockout penalties.", bullet_style))
    story.append(Paragraph("• <b>Razorpay Subscription Billing:</b> Multi-tier billing management (Growth, Scale, Enterprise) supporting checkout verification, webhooks, and tier usage tracking.", bullet_style))

    story.append(Paragraph("In-Progress & Roadmap Items", h2_style))
    story.append(Paragraph("• <i>Razorpay Live Production Execution:</i> Execution of live key checkout verification in production payment mode.", bullet_style))
    story.append(Paragraph("• <i>Firebase Token Custom Claims Sync:</i> Real-time custom claims sync on dynamic industry change in production Firebase auth mode.", bullet_style))
    story.append(Paragraph("• <i>Enterprise Connector Expansion:</i> Expanding built-in connectors to match the complete 30+ advertised enterprise catalog.", bullet_style))

    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # 3. MODELS
    # ----------------------------------------------------------------------
    story.append(Paragraph("3. MODELS", h1_style))
    
    story.append(Paragraph("ML & AI Forecasting Models Stack", h2_style))
    story.append(Paragraph(
        "SANKET incorporates a multi-tiered ensemble of statistical, gradient boosted, deep learning, foundation, and causal models located in <code>backend/ml/sanket_ml/models/</code>:",
        body_style
    ))

    ml_models_data = [
        [Paragraph("<b>Model Category</b>", table_header_style), Paragraph("<b>Model Name & Module Path</b>", table_header_style), Paragraph("<b>Purpose & Implementation Details</b>", table_header_style)],
        [
            Paragraph("<b>Foundation Models</b>", table_cell_style),
            Paragraph("• Chronos (<code>foundation/chronos.py</code>)<br/>• Lag-Llama (<code>foundation/lag_llama.py</code>)<br/>• Moirai (<code>foundation/moirai.py</code>)<br/>• TimesFM (<code>foundation/timesfm.py</code>)", table_cell_style),
            Paragraph("Pre-trained time-series foundation models. Amazon Chronos T5 Small provides instant zero-shot baseline forecasts without prior model training.", table_cell_style)
        ],
        [
            Paragraph("<b>Deep Learning</b>", table_cell_style),
            Paragraph("• DeepAR (<code>deep/deepar.py</code>)<br/>• N-HiTS (<code>deep/nhits.py</code>)<br/>• TFT (<code>deep/tft.py</code>)", table_cell_style),
            Paragraph("PyTorch Lightning & Darts deep forecasters capturing non-linear temporal interactions, static covariates, and multi-horizon outputs.", table_cell_style)
        ],
        [
            Paragraph("<b>Gradient Boosting</b>", table_cell_style),
            Paragraph("LightGBM Forecaster (<code>gradient_boost/lightgbm_forecaster.py</code>)", table_cell_style),
            Paragraph("LightGBM wrapped with <code>mlforecast</code> for high-speed tabular feature engineering (lags, rolling stats, calendar features).", table_cell_style)
        ],
        [
            Paragraph("<b>Statistical / Intermittent</b>", table_cell_style),
            Paragraph("• Croston (<code>statistical/croston.py</code>)<br/>• ETS (<code>statistical/ets.py</code>)<br/>• Naive (<code>statistical/naive.py</code>)<br/>• ADIDA (<code>adida.py</code>)", table_cell_style),
            Paragraph("StatsForecast baselines. Croston and ADIDA specifically handle sparse, intermittent, and low-volume SKU demand profiles.", table_cell_style)
        ],
        [
            Paragraph("<b>Ensemble & Meta</b>", table_cell_style),
            Paragraph("• Stacked Ensemble (<code>ensemble.py</code>)<br/>• Meta Learner (<code>meta_learner.py</code>)", table_cell_style),
            Paragraph("Solves SLSQP convex optimization to minimize pinball loss across holdout windows, producing optimal convex model weights.", table_cell_style)
        ],
        [
            Paragraph("<b>Causal & Elasticity</b>", table_cell_style),
            Paragraph("• DoWhy Causal (<code>causal/dowhy_pipeline.py</code>)<br/>• Uplift Model (<code>causal/uplift.py</code>)<br/>• Price Elasticity (<code>price_elasticity.py</code>)", table_cell_style),
            Paragraph("EconML & DoWhy causal graphs estimating treatment effects of marketing promotions, price adjustments, and market shocks.", table_cell_style)
        ],
        [
            Paragraph("<b>Optimization</b>", table_cell_style),
            Paragraph("• EOQ (<code>optimization/eoq.py</code>)<br/>• Markdown (<code>optimization/markdown.py</code>)<br/>• Replenishment (<code>optimization/replenishment.py</code>)<br/>• RL Planner (<code>optimization/rl_replenishment.py</code>)", table_cell_style),
            Paragraph("Google OR-Tools and Ray RLlib algorithms solving multi-echelon inventory replenishment, safety stock, and markdown pricing.", table_cell_style)
        ]
    ]
    ml_table = Table(ml_models_data, colWidths=[100, 180, 260])
    ml_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT])
    ]))
    story.append(ml_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Key Database Entities & Schemas", h2_style))
    story.append(Paragraph(
        "The relational data model defined in <code>backend/sql/002_schema.sql</code> and Alembic migrations comprises 31+ core tables:",
        body_style
    ))
    story.append(Paragraph("• <b>tenants & users:</b> Root tenancy entity (slug, tier, active_industry, max_skus) and user accounts with Argon2 password hashes, Firebase UIDs, and 4-tier roles.", bullet_style))
    story.append(Paragraph("• <b>industries & industry_profiles:</b> Global industry lookup (default horizon, required signals, model lists, audit levels) and tenant-specific profile overrides.", bullet_style))
    story.append(Paragraph("• <b>products & skus:</b> Product catalog and granular SKU records (gtin, lead_time_days, moq, safety_stock, reorder_point, cost, price, attributes JSONB).", bullet_style))
    story.append(Paragraph("• <b>historical_sales (Partitioned):</b> Range-partitioned quarterly (2022–2027) storing sales transactions, channel, region, units sold, revenue, and in_stock flags.", bullet_style))
    story.append(Paragraph("• <b>pharma_batches (GxP):</b> Pharmaceutical lot tracking (lot_number, ndc_code, expiry_date, gxp_status, cold_chain_required, storage_temp min/max, qa_released_by).", bullet_style))
    story.append(Paragraph("• <b>external_signals & signal_clusters:</b> Market signals (sentiment, processed values) and pgvector 768-dim HNSW vector embedding centroid clusters.", bullet_style))
    story.append(Paragraph("• <b>forecast_runs & forecast_results (Partitioned):</b> Execution run metadata and quarterly range-partitioned percentile demand predictions (p10, p50, p90).", bullet_style))
    story.append(Paragraph("• <b>audit_log:</b> Immutable 21 CFR Part 11 append-only audit trail protected by PostgreSQL NO-UPDATE and NO-DELETE rules.", bullet_style))

    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # 4. FUNCTIONS & FUNCTIONALITIES
    # ----------------------------------------------------------------------
    story.append(Paragraph("4. FUNCTIONS & FUNCTIONALITIES", h1_style))
    
    story.append(Paragraph("Core Modules & Service Layer", h2_style))
    
    fn_data = [
        [Paragraph("<b>Module Path</b>", table_header_style), Paragraph("<b>Key Functions & Classes</b>", table_header_style), Paragraph("<b>Core Responsibility</b>", table_header_style)],
        [
            Paragraph("<code>backend/app/core/database.py</code>", table_cell_style),
            Paragraph("• <code>Database.session(tenant_id)</code><br/>• <code>session_no_rls()</code><br/>• <code>assert_tenant_isolation_enforced()</code>", table_cell_style),
            Paragraph("Manages async SQLAlchemy engine, sets <code>app.current_tenant_id</code> per session, and enforces RLS security assertions on startup.", table_cell_style)
        ],
        [
            Paragraph("<code>backend/app/core/rbac.py</code>", table_cell_style),
            Paragraph("• <code>require_role()</code><br/>• <code>require_role_db()</code><br/>• <code>require_admin()</code>", table_cell_style),
            Paragraph("Enforces 4-role RBAC authorization (owner, admin, analyst, viewer) with DB re-verification for state-modifying operations.", table_cell_style)
        ],
        [
            Paragraph("<code>backend/app/services/hybrid_forecast.py</code>", table_cell_style),
            Paragraph("• <code>HybridForecastService.generate_forecast()</code><br/>• <code>_call_ml_api()</code>", table_cell_style),
            Paragraph("Orchestrates forecast generation by calling the ML API or invoking zero-shot Chronos, storing results to <code>forecast_results</code>.", table_cell_style)
        ],
        [
            Paragraph("<code>backend/app/services/billing/subscription_manager.py</code>", table_cell_style),
            Paragraph("• <code>SubscriptionManager.create_subscription()</code><br/>• <code>check_entitlement()</code>", table_cell_style),
            Paragraph("Handles Razorpay subscription lifecycle, plan upgrades, tier SKU limit checks, and active subscription verification.", table_cell_style)
        ],
        [
            Paragraph("<code>backend/app/services/external_signals/signal_pipeline.py</code>", table_cell_style),
            Paragraph("• <code>SignalPipeline.run_ingestion()</code><br/>• <code>_cluster_signals()</code>", table_cell_style),
            Paragraph("Executes multi-connector signal ingestion, processes sentiment scores, and builds pgvector HNSW embeddings.", table_cell_style)
        ],
        [
            Paragraph("<code>backend/app/services/integrations/file_import.py</code>", table_cell_style),
            Paragraph("• <code>FileImportService.process_file()</code><br/>• <code>_validate_rows()</code>", table_cell_style),
            Paragraph("Parses uploaded CSV/XLSX sales feeds, validates column schemas, and performs bulk upserts into <code>historical_sales</code>.", table_cell_style)
        ],
        [
            Paragraph("<code>backend/app/workers/forecast_worker.py</code>", table_cell_style),
            Paragraph("• <code>WorkerSettings</code><br/>• <code>run_hybrid_forecast_job()</code>", table_cell_style),
            Paragraph("Durable background job worker powered by <code>arq</code> and Redis for non-blocking asynchronous forecasting tasks.", table_cell_style)
        ]
    ]
    fn_table = Table(fn_data, colWidths=[140, 160, 240])
    fn_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT])
    ]))
    story.append(fn_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("API Routers & Background Processing", h2_style))
    story.append(Paragraph("• <b>Auth & Tenant Routers (<code>auth.py</code>, <code>industry_router.py</code>):</b> Login, signup, JWT issuance, MFA verification, and <code>/industry/activate</code> workspace switching.", bullet_style))
    story.append(Paragraph("• <b>Forecast & Analytics Routers (<code>forecasts.py</code>, <code>hybrid_forecast.py</code>, <code>sales_analytics.py</code>):</b> Submitting forecast runs, retrieving P10/P50/P90 time series, and analyzing sales metrics.", bullet_style))
    story.append(Paragraph("• <b>Industry Vertical Routers (<code>fashion.py</code>, <code>electronics.py</code>, <code>pharma.py</code>, <code>agrocenter.py</code>, <code>hardware.py</code>):</b> Specialized endpoints returning vertical KPIs, batch release actions, and BOM alerts.", bullet_style))
    story.append(Paragraph("• <b>Billing & Subscription Router (<code>billing.py</code>):</b> Plan listings, checkout sessions, Razorpay webhooks, and usage metrics.", bullet_style))
    story.append(Paragraph("• <b>Background Workers:</b> <code>arq</code> worker executing background forecast jobs; background pollers for e-commerce sync (Shopify, WooCommerce) and external signals.", bullet_style))

    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # 5. USES
    # ----------------------------------------------------------------------
    story.append(Paragraph("5. USES", h1_style))
    
    story.append(Paragraph("End-to-End Operational Scenarios", h2_style))

    story.append(Paragraph("Scenario A: Fashion Retailer Markdown & Seasonality Optimization", h2_style))
    story.append(Paragraph(
        "1. <i>Data Ingestion:</i> Demand planner uploads 2 years of seasonal sales history via <code>file_import.py</code>.<br/>"
        "2. <i>Forecasting:</i> Platform triggers 5-stage ML pipeline. <code>StackedEnsemble</code> fits LightGBM + Croston + DeepAR on seasonal apparel panel.<br/>"
        "3. <i>Signal Fusion:</i> Google Trends connector (<code>trends_connector.py</code>) detects declining trend for summer apparel styles.<br/>"
        "4. <i>Optimization:</i> System invokes <code>markdown.py</code> to generate an optimal weekly price reduction schedule that maximizes gross margin while liquidating inventory before autumn season launch.<br/>"
        "5. <i>Execution:</i> Planner reviews P10/P50/P90 forecasts on <code>FashionDashboard.tsx</code> and pushes markdown prices to e-commerce channels.",
        body_style
    ))

    story.append(Paragraph("Scenario B: Pharmaceutical GxP Cold-Chain & Expiry Management", h2_style))
    story.append(Paragraph(
        "1. <i>Tenant Onboarding:</i> Customer activates Pharmaceutical workspace (<code>pharma</code>). Backend sets audit level to <code>gxp</code> and enforces 52-week horizon.<br/>"
        "2. <i>Batch Registration:</i> Production line registers new vaccine batch (lot #, NDC code, manufacture/expiry dates, storage range: -20°C to -15°C).<br/>"
        "3. <i>Regulatory Monitoring:</i> <code>fda_connector.py</code> scans FDA enforcement reports for competing drug recall notices.<br/>"
        "4. <i>QA Release Workflow:</i> QA Lead inspects batch temp logs and signs digital release (<code>qa_released_by</code>). Backend records append-only event in <code>audit_log</code>.<br/>"
        "5. <i>Shortage Prevention:</i> Zero-shot Chronos forecaster detects impending regional clinic stockout 12 weeks out, prompting automatic replenishment.",
        body_style
    ))

    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # 6. ARCHITECTURE
    # ----------------------------------------------------------------------
    story.append(Paragraph("6. ARCHITECTURE", h1_style))
    
    story.append(Paragraph("Full Technology Stack Summary", h2_style))
    
    stack_data = [
        [Paragraph("<b>Layer</b>", table_header_style), Paragraph("<b>Technologies & Frameworks</b>", table_header_style), Paragraph("<b>Role in System</b>", table_header_style)],
        [Paragraph("Frontend", table_cell_style), Paragraph("Vite 5, React 18, TypeScript 5.6, Tailwind CSS, TanStack Query, Zustand, Recharts", table_cell_style), Paragraph("Single Page Application dashboard delivering responsive charts, workspace switching, and real-time updates.", table_cell_style)],
        [Paragraph("Backend API", table_cell_style), Paragraph("FastAPI 0.115, Python 3.12, Uvicorn, Pydantic v2, SQLAlchemy 2.0 (asyncio), asyncpg", table_cell_style), Paragraph("Asynchronous REST API, RBAC, tenant context middleware, billing, and integrations.", table_cell_style)],
        [Paragraph("ML Engine", table_cell_style), Paragraph("PyTorch 2.4, LightGBM 4.5, Amazon Chronos 1.4, StatsForecast, OR-Tools 9.11, DoWhy", table_cell_style), Paragraph("Dedicated ML inference API (:8001), 5-stage training pipeline, causal graphs, zero-shot forecaster.", table_cell_style)],
        [Paragraph("Database", table_cell_style), Paragraph("PostgreSQL 16, pgvector (0.7+), Row-Level Security (RLS), Declarative Partitioning", table_cell_style), Paragraph("Primary datastore enforcing strict tenant isolation, 768-dim vector search, quarterly range partitions.", table_cell_style)],
        [Paragraph("Cache / Worker", table_cell_style), Paragraph("Redis 7, <code>arq</code> (async Redis job queue)", table_cell_style), Paragraph("Session caching, rate limiting, and durable background hybrid forecast job queue execution.", table_cell_style)],
        [Paragraph("DevOps / Infra", table_cell_style), Paragraph("Docker Compose, Kubernetes (Kustomize), Nginx, Prometheus 2.54, Grafana 11.2", table_cell_style), Paragraph("Container orchestration, ingress reverse proxying, metrics collection, and operational dashboards.", table_cell_style)]
    ]
    s_table = Table(stack_data, colWidths=[80, 210, 250])
    s_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), SECONDARY),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT])
    ]))
    story.append(s_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("System Architecture & Data Flow Diagram", h2_style))
    
    diagram_text = (
        "+-----------------------------------------------------------------------------------+\n"
        "|                        CLIENT LAYER (Nginx Ingress / TLS)                         |\n"
        "+-----------------------------------------------------------------------------------+\n"
        "       | / (Static Assets)                  | /api/v1 (REST / WS)             | /ml (Inference)\n"
        "       v                                    v                                 v\n"
        "+-------------------+             +-------------------+             +-------------------+\n"
        "|   React SPA       |             |  FastAPI Backend  |             |  ML Inference API |\n"
        "|   Vite + TS       |             |  (port 8000)      |------------>|  (port 8001)      |\n"
        "|   Port 8080       |             |  • Tenant RLS     |   HTTPX     |  • Chronos T5     |\n"
        "+-------------------+             |  • Industry Router|   Bearer    |  • Joblib Ensembles|\n"
        "                                  |  • GxP Batch Audit|             |  • OR-Tools Supply|\n"
        "                                  +-------------------+             +-------------------+\n"
        "                                            |                                 |\n"
        "                       +--------------------+---------------------------------+\n"
        "                       |                                     |\n"
        "                       v                                     v\n"
        "+-----------------------------------+             +-----------------------------------+\n"
        "|        PostgreSQL 16 + RLS        |             |         Redis 7 + arq Queue       |\n"
        "| • pgvector 768-dim HNSW Indexing  |             | • Session & Rate-Limit Cache      |\n"
        "| • Range-Partitioned Sales & Results|             | • Asynchronous Background Worker  |\n"
        "| • Immutable Audit Trail (SQL Rules|             | • Webhook Delivery & PubSub       |\n"
        "+-----------------------------------+             +-----------------------------------+"
    )
    
    diagram_table = Table([[Paragraph(f"<pre>{diagram_text}</pre>", code_style)]], colWidths=[540])
    diagram_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(diagram_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Key Architectural Design Decisions & Tradeoffs", h2_style))
    story.append(Paragraph("1. <b>Shared Database Schema with PostgreSQL RLS vs. Database-per-Tenant:</b><br/>"
                           "<i>Decision:</i> Utilize PostgreSQL Row-Level Security (RLS) driven by <code>app.current_tenant_id</code>.<br/>"
                           "<i>Tradeoff:</i> Drastically reduces database infrastructure cost and simplifies schema migrations across hundreds of tenants. The tradeoff is strict reliance on session initialization; mitigated by startup role assertions (refusing to boot if the DB role bypasses RLS) and <code>FORCE RLS</code> on all tables.", body_style))
    story.append(Paragraph("2. <b>Decoupled Microservice ML API vs. Monolithic API:</b><br/>"
                           "<i>Decision:</i> Separate the ML inference stack into a dedicated FastAPI service on port 8001.<br/>"
                           "<i>Tradeoff:</i> Prevents heavy PyTorch/Transformers CPU/GPU memory loads and long inference compute from blocking the web API event loop. The tradeoff is inter-service HTTP latency and model artifact file sync requirements.", body_style))

    story.append(Spacer(1, 8))

    # ----------------------------------------------------------------------
    # 7. COMPLETE PROJECT VIEW
    # ----------------------------------------------------------------------
    story.append(Paragraph("7. COMPLETE PROJECT VIEW", h1_style))
    
    story.append(Paragraph("Holistic Synthesis & Project Maturity", h2_style))
    story.append(Paragraph(
        "SANKET represents a highly sophisticated, production-grade engineering foundation designed for enterprise supply chain analytics. The core data tier, multi-tenant isolation model, 5-stage ML forecasting engine, and specialized vertical contexts demonstrate exceptional architectural rigor. With recent fixes to subscription entitlement enforcement and workspace token re-minting, the backend core is ready for cloud deployment.",
        body_style
    ))

    story.append(Paragraph("Known Limitations & Verified Gaps", h2_style))
    story.append(Paragraph("• <b>Razorpay Payment Gateway Verification:</b> Subscription revenue-path models and entitlement guards (HTTP 402) are functional, but live payment checkouts require configuration of production Razorpay API keys.", bullet_style))
    story.append(Paragraph("• <b>Firebase Auth Custom Claims in Prod Mode:</b> Token claims refresh correctly in dev-login fallback mode; production Firebase mode requires cloud project verification for custom claims synchronization on workspace change.", bullet_style))
    story.append(Paragraph("• <b>Connector Integration Catalog Expansion:</b> Built-in connectors (Shopify, WooCommerce, SQL Source, File Importer, 7 External Signal Connectors) are complete; expanding to the full 30+ enterprise connector catalog remains an ongoing phase.", bullet_style))

    story.append(Paragraph("Strategic Next Steps & Recommendations", h2_style))
    story.append(Paragraph("1. <i>Execute Live Payment Checkout Test:</i> Provide sandbox Razorpay API keys to test end-to-end checkout, invoice generation, and webhook handling.", bullet_style))
    story.append(Paragraph("2. <i>Deploy Staging Environment to Cloud:</i> Provision managed PostgreSQL 16 (Cloud SQL / RDS) with pgvector and deploy backend/ml services to Cloud Run / GKE using existing Kustomize manifests.", bullet_style))
    story.append(Paragraph("3. <i>Expand Automated Frontend E2E Tests:</i> Extend Playwright test coverage across paywall gates, workspace switching, and GxP batch release workflows.", bullet_style))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceBefore=4, spaceAfter=8))
    story.append(Paragraph("<i>Report compiled automatically from codebase audit of Sanket-Project / Prisma workspace.</i>", meta_callout_style))

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully generated at: {os.path.abspath(filename)}")

if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "SANKET_Comprehensive_Project_Report.pdf"
    build_pdf(out_path)
