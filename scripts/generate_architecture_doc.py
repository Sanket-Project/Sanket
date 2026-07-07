import os
import sys
import uuid
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and draw 'Page X of Y' 
    along with running headers and footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        # Page 1 is the cover page - skip header/footer
        if self._pageNumber == 1:
            return
            
        self.saveState()
        
        # Primary Brand Color: Deep Navy Blue (#1A365D)
        # Secondary Brand Color: Teal (#319795)
        # Accent Color: Slate Grey (#4A5568)
        # Neutral Grey: Light (#E2E8F0)
        
        # Running Header
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#1A365D"))
        self.drawString(54, 750, "SANKET PLATFORM SPECIFICATION")
        
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawRightString(558, 750, "Architecture & Authentication Flow")
        
        # Header Rule
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.75)
        self.line(54, 742, 558, 742)
        
        # Footer Rule
        self.line(54, 55, 558, 55)
        
        # Footer
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#E53E3E"))
        self.drawString(54, 40, "CONFIDENTIAL")
        
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawString(135, 40, "— Internal Product Engineering and Architecture Document")
        
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        
        self.restoreState()

def build_pdf(filename="SANKET_Architecture_and_Flows.pdf"):
    # Target path inside docs directory
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=72,
        bottomMargin=72
    )

    styles = getSampleStyleSheet()
    
    # Custom styles to build a premium visual aesthetic
    primary_color = colors.HexColor("#1A365D")
    secondary_color = colors.HexColor("#319795")
    charcoal = colors.HexColor("#2D3748")
    
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=30,
        leading=36,
        textColor=primary_color,
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=14,
        leading=20,
        textColor=secondary_color,
        spaceAfter=40
    )
    
    meta_style = ParagraphStyle(
        'CoverMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#718096")
    )
    
    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=primary_color,
        spaceBefore=18,
        spaceAfter=10,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=secondary_color,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=charcoal,
        spaceAfter=8
    )

    body_bold_style = ParagraphStyle(
        'DocBodyBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    
    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )

    code_style = ParagraphStyle(
        'DocCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1A202C"),
        backColor=colors.HexColor("#F7FAFC"),
        borderColor=colors.HexColor("#E2E8F0"),
        borderWidth=0.5,
        borderPadding=6,
        spaceAfter=10
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=charcoal
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=table_cell_style,
        fontName='Helvetica-Bold'
    )

    story = []

    # ==========================================
    # COVER PAGE
    # ==========================================
    story.append(Spacer(1, 100))
    # Brand line
    d_block = Table([['']], colWidths=[504], rowHeights=[6])
    d_block.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), secondary_color),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(d_block)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("SANKET SaaS Platform", title_style))
    story.append(Paragraph("TECHNICAL SPECIFICATION MANUAL<br/>Architecture, System Flows, and Onboarding Journeys", subtitle_style))
    
    story.append(Spacer(1, 180))
    
    meta_text = (
        "<b>Document Type:</b> Product Architecture and Flow Specification<br/>"
        "<b>Version:</b> 1.0 (Enterprise Release)<br/>"
        "<b>Date:</b> June 2026<br/>"
        "<b>Security:</b> Restricted / Confidential<br/>"
        "<b>Target Audience:</b> Engineering, Product Management, Security, and Customer Success Teams"
    )
    story.append(Paragraph(meta_text, meta_style))
    story.append(PageBreak())

    # ==========================================
    # SECTION 1: SYSTEM ARCHITECTURE
    # ==========================================
    story.append(Paragraph("1. System Architecture Overview", h1_style))
    story.append(Paragraph(
        "SANKET is a vertically-integrated, multi-tenant Software-as-a-Service (SaaS) platform "
        "designed to deliver predictive forecasting and supply chain optimization across multiple "
        "industry verticals, specifically <b>Apparel & Fashion</b>, <b>Consumer Electronics</b>, and "
        "<b>Pharmaceuticals</b> (compliant with GxP and 21 CFR Part 11).",
        body_style
    ))
    story.append(Paragraph(
        "The platform utilizes a modern containerized micro-frontend and API architecture backed "
        "by PostgreSQL with strict Row-Level Security (RLS) for tenant isolation. The diagram below "
        "and subsequent tables describe the high-level layout of the application components:",
        body_style
    ))

    # Architecture Table Diagram
    arch_data = [
        [Paragraph("<b>Component</b>", table_header_style), Paragraph("<b>Technology Stack</b>", table_header_style), Paragraph("<b>Core Responsibility</b>", table_header_style)],
        [Paragraph("<b>Frontend SPA</b>", table_cell_bold), Paragraph("Vite + React + TypeScript<br/>Nginx (Port 8080)", table_cell_style), Paragraph("Single-page app displaying real-time supply chain metrics, demand forecasts, GxP audits, and tenant configurations.", table_cell_style)],
        [Paragraph("<b>Backend API</b>", table_cell_bold), Paragraph("FastAPI (Python 3.11+)<br/>Uvicorn (Port 8000)", table_cell_style), Paragraph("Handles auth (JWT/Firebase), workspace routing, metadata CRUD, audit logging, and logical tenant separation middleware.", table_cell_style)],
        [Paragraph("<b>ML Inference API</b>", table_cell_bold), Paragraph("FastAPI (Python)<br/>Ensemble + Chronos (Port 8001)", table_cell_style), Paragraph("Serves predictive forecasts using pre-trained stacked ensembles or falls back to Amazon Chronos Zero-Shot deep learning models.", table_cell_style)],
        [Paragraph("<b>Database</b>", table_cell_bold), Paragraph("PostgreSQL 16 + pgvector<br/>Strict Row-Level Security (RLS)", table_cell_style), Paragraph("Contains shared relational schemas. Tenant isolation is enforced at the DB-connection level using tenant UUIDs.", table_cell_style)]
    ]
    
    t_arch = Table(arch_data, colWidths=[110, 140, 254])
    t_arch.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    story.append(t_arch)
    story.append(Spacer(1, 15))

    story.append(Paragraph("1.1 Multi-Tenant Row-Level Security (RLS)", h2_style))
    story.append(Paragraph(
        "To ensure complete logical isolation between enterprise customers (tenants):",
        body_style
    ))
    story.append(Paragraph(
        "• <b>Tenant Boundary:</b> Every database table containing customer-owned data includes a <code>tenant_id</code> UUID column.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <b>Connection Setting:</b> For every incoming API request, the FastAPI database session helper issues a <code>SET LOCAL app.current_tenant_id = '&lt;uuid&gt;'</code> command.",
        bullet_style
    ))
    story.append(Paragraph(
        "• <b>Database Enforcement:</b> PostgreSQL Row-Level Security (RLS) policies block any read, update, or delete operations that do not match the current session's tenant ID. This prevents cross-tenant data leaks at the query execution level.",
        bullet_style
    ))
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 2: AUTHENTICATION & ONBOARDING JOURNEYS
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("2. Onboarding & Authentication Journeys", h1_style))
    story.append(Paragraph(
        "This section details the explicit user journeys and backend mechanics for the three entry points: "
        "<b>Self-Service Sign-Up</b>, <b>Demo Sandbox</b>, and <b>Standard Sign-In</b>.",
        body_style
    ))

    # Journey 1
    story.append(Paragraph("2.1 Journey A: Self-Service Sign-Up", h2_style))
    story.append(Paragraph(
        "This flow allows a new organization to establish a brand-new tenant account. Self-service sign-up "
        "strictly prevents users from joining existing tenant workspaces to avoid unauthorized entry into another customer's data.",
        body_style
    ))

    signup_steps = [
        ("1. Input", "User goes to '/login?mode=signup' and inputs their Full Name, Email, Password, and a desired Tenant Slug (e.g., 'acme-pharma')."),
        ("2. Request", "Frontend sends a POST request to '/api/v1/auth/signup' containing registration details."),
        ("3. Validation", "Backend performs checks:\n- Email is checked for uniqueness in the database.\n- Tenant Slug is checked to ensure no tenant exists with that name. If it exists, a ConflictError is thrown."),
        ("4. DB Provisioning", "The backend creates:\n- A new Tenant record (status: Trial, tier: Growth) with allowed verticals.\n- Default IndustryProfile configurations (enabling vertical-specific feature flags like GxP mode for Pharma).\n- A new User record (role: Owner) with password hashed using Argon2id."),
        ("5. Firebase Sync", "If Firebase is enabled, backend creates the user in Firebase Auth and immediately assigns custom tenant claims: tid (Tenant ID), puid (User ID), role (owner), ind (active industry)."),
        ("6. Response", "The backend returns an 'ok' status, redirecting the user to sign-in.")
    ]

    t_signup_data = [[Paragraph("<b>Step</b>", table_header_style), Paragraph("<b>Action & Backend Logic</b>", table_header_style)]]
    for step, desc in signup_steps:
        t_signup_data.append([
            Paragraph(f"<b>{step}</b>", table_cell_bold),
            Paragraph(desc.replace('\n', '<br/>'), table_cell_style)
        ])

    t_signup = Table(t_signup_data, colWidths=[100, 404])
    t_signup.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C7A7B")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0FDF4")]),
    ]))
    story.append(t_signup)
    story.append(Spacer(1, 15))

    # Journey 2
    story.append(Paragraph("2.2 Journey B: 'Try the Sandbox' (Public Demo Access)", h2_style))
    story.append(Paragraph(
        "To let prospective clients evaluate SANKET without registering, the 'Try the Sandbox' flow "
        "authenticates them into a pre-seeded public tenant account. Crucially, this happens passwordlessly and "
        "entirely server-side so no credentials are ever exposed in client-side bundles.",
        body_style
    ))

    sandbox_steps = [
        ("1. UI Click", "User clicks 'Try the Sandbox' on the marketing page."),
        ("2. Session Call", "Frontend sends a empty-body POST to '/api/v1/auth/sandbox-session'."),
        ("3. Tenant Resolution", "Backend checks configurations to find the configured sandbox tenant slug ('sanket-dev') and sandbox email ('owner@sanket-dev.com')."),
        ("4. Token Minting", "The backend creates a custom auth token representing the demo tenant/owner user. The token encodes custom tenant claims (tid, puid, role, active_industry)."),
        ("5. Audit Log", "Backend commits a 'user.sandbox_login' event in the central database audit table (recording timestamp, IP, and user-agent)."),
        ("6. Session Start", "The backend returns the SandboxSessionResponse containing the JWT/Firebase custom token. The React SPA stores it and authenticates the user instantly, redirecting them to the live dashboard.")
    ]

    t_sandbox_data = [[Paragraph("<b>Step</b>", table_header_style), Paragraph("<b>Action & Backend Logic</b>", table_header_style)]]
    for step, desc in sandbox_steps:
        t_sandbox_data.append([
            Paragraph(f"<b>{step}</b>", table_cell_bold),
            Paragraph(desc, table_cell_style)
        ])

    t_sandbox = Table(t_sandbox_data, colWidths=[110, 394])
    t_sandbox.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    story.append(t_sandbox)
    story.append(Spacer(1, 15))

    # Journey 3
    story.append(PageBreak())
    story.append(Paragraph("2.3 Journey C: Standard Sign-In & API Security", h2_style))
    story.append(Paragraph(
        "Once a user has an active account, standard sign-in authenticates them and injects tenant-context "
        "claims into all subsequent API traffic.",
        body_style
    ))
    story.append(Paragraph(
        "<b>1. Credentials Check:</b> The user enters their email and password. The backend verifies the password hash (Argon2id) or validates a Google OAuth ID token.<br/>"
        "<b>2. JWT Generation:</b> The backend issues a JWT containing custom claims: <code>tid</code> (Tenant ID UUID), <code>role</code> (e.g. Owner, Analyst), <code>ind</code> (Active Industry), and <code>industries</code> (Licensed verticals). Access tokens expire in 60 minutes; refresh tokens are stored as SHA-256 hashes for security.<br/>"
        "<b>3. Client-Side Storage:</b> The Vite + React SPA receives the token, stores it in <code>useAuthStore</code>, and attaches it as a Bearer token in the <code>Authorization</code> header of every Axios API request.<br/>"
        "<b>4. TenantContextMiddleware:</b> For every request, backend middleware intercepts the token, extracts the claims, verifies signature, and writes details to <code>request.state</code>. When query runs, the middleware applies the tenant filter to the database session, enforcing strict RLS.",
        body_style
    ))
    
    # Simple flow diagram styled as a table
    flow_diagram_data = [
        [Paragraph("<b>Step 1: Sign-In Page</b>", table_cell_bold), Paragraph("<b>Step 2: Backend API</b>", table_cell_bold), Paragraph("<b>Step 3: Database Session</b>", table_cell_bold)],
        [
            Paragraph("User enters password. Client POSTs to `/auth/login`.", table_cell_style),
            Paragraph("Verifies hash, issues JWT with tenant ID (`tid`) & role claims.", table_cell_style),
            Paragraph("Saves login event to append-only `audit_log`.", table_cell_style)
        ],
        [
            Paragraph("<b>Step 4: SPA Storage</b>", table_cell_bold),
            Paragraph("<b>Step 5: Middleware</b>", table_cell_bold),
            Paragraph("<b>Step 6: RLS Enforcement</b>", table_cell_bold)
        ],
        [
            Paragraph("SPA stores JWT, appends it as `Authorization: Bearer <token>` to requests.", table_cell_style),
            Paragraph("`TenantContextMiddleware` intercepts, parses `tid`, and binds it to database session.", table_cell_style),
            Paragraph("`SET LOCAL app.current_tenant_id` blocks any SQL commands targeting other tenants.", table_cell_style)
        ]
    ]
    t_flow = Table(flow_diagram_data, colWidths=[168, 168, 168])
    t_flow.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4A5568")),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor("#4A5568")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, 1), [colors.HexColor("#F7FAFC")]),
        ('ROWBACKGROUNDS', (0, 3), (-1, 3), [colors.HexColor("#F7FAFC")]),
    ]))
    story.append(t_flow)
    story.append(Spacer(1, 20))

    # ==========================================
    # SECTION 3: AFTER SIGN-IN (WHAT USER GETS)
    # ==========================================
    story.append(Paragraph("3. After Sign-In: What the User Gets", h1_style))
    story.append(Paragraph(
        "Upon successful authentication (either standard or via the sandbox), the user is redirected to the "
        "main Dashboard. What the user sees and is authorized to do depends on their active industry vertical, "
        "role permissions, and tenant tier.",
        body_style
    ))

    # Multi-vertical
    story.append(Paragraph("3.1 Vertical Industry Dashboards", h2_style))
    story.append(Paragraph(
        "SANKET dynamically adapts its user interface based on the active industry. Users can toggle between "
        "industries via a selector in the header (which overrides the default backend vertical by sending the "
        "<code>X-Industry-Code</code> header):",
        body_style
    ))

    vertical_data = [
        [Paragraph("<b>Vertical</b>", table_header_style), Paragraph("<b>Key UI Modules & Capabilities Provided</b>", table_header_style)],
        [
            Paragraph("<b>Apparel & Fashion</b>", table_cell_bold),
            Paragraph(
                "• <b>Style Demand Forecasting:</b> Forecasts styles with short lifecycles, seasonal trends, and high product variety.<br/>"
                "• <b>Assortment Planning:</b> Guides store-level distribution, color, and size breakdown based on historic sales profiles.<br/>"
                "• <b>Markdown Optimizer:</b> Simulates price-decay strategies to clear seasonal stock while maximizing margins.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>Consumer Electronics</b>", table_cell_bold),
            Paragraph(
                "• <b>Lifecycle Sales Forecasting:</b> Predicts demand curves for new launches, incorporating obsolescence profiles.<br/>"
                "• <b>Component Risk Tracker:</b> Evaluates raw component supply dependencies and tracks vendor risk scores.<br/>"
                "• <b>Competitor Tracker:</b> Visualizes real-time competitor prices scraped from online marketplaces.",
                table_cell_style
            )
        ],
        [
            Paragraph("<b>Pharmaceuticals</b>", table_cell_bold),
            Paragraph(
                "• <b>GxP Batch Compliance:</b> Displays batch numbers, manufacturing dates, and cold-chain temperature logs. Requires strict QA-release approvals before dispatching forecasts.<br/>"
                "• <b>Drug Shortage Predictor:</b> Identifies API (Active Pharmaceutical Ingredient) bottlenecks and predicts risk of regulatory stockouts.<br/>"
                "• <b>Immutable Audit Log:</b> Lists every user action in an append-only ledger, compliant with 21 CFR Part 11 regulations.",
                table_cell_style
            )
        ]
    ]

    t_vert = Table(vertical_data, colWidths=[130, 374])
    t_vert.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C7A7B")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0FDF4")]),
    ]))
    story.append(t_vert)
    story.append(Spacer(1, 15))

    # Predictive Forecasting
    story.append(PageBreak())
    story.append(Paragraph("3.2 Predictive Forecasting Engine", h2_style))
    story.append(Paragraph(
        "Users get access to a powerful demand forecasting pipeline. When a user requests a forecast (via the UI or API), "
        "SANKET dynamically routes the demand series:",
        body_style
    ))
    story.append(Paragraph(
        "1. <b>Trained Ensemble Path:</b> If the tenant has seeded data and completed a training pass, the platform loads the "
        "pre-trained <code>StackedEnsemble</code> model bundle (combining statistical models, GBT, deep neural nets, and foundation forecasters) "
        "to generate precise forecasts optimized for their historical patterns.",
        body_style
    ))
    story.append(Paragraph(
        "2. <b>Zero-Shot Fallback:</b> During onboarding or right after signup, when no custom models are trained yet, the backend transparently "
        "routes requests to a <code>ZeroShotForecaster</code> using Amazon's <b>Chronos zero-shot deep learning model</b>. This ensures the user gets "
        "valuable predictions instantly without needing prior model training.",
        body_style
    ))
    story.append(Spacer(1, 10))

    # Supply Chain Optimization
    story.append(Paragraph("3.3 Supply Chain & Inventory Optimization", h2_style))
    story.append(Paragraph(
        "SANKET translates demand forecasts directly into actionable logistics advice. The Inventory Optimization module provides:<br/>"
        "• <b>Safety Stock Calculator:</b> Calculates optimal stock buffers considering vendor lead-time variability and target service levels (e.g., 95% or 99% service rate).<br/>"
        "• <b>Reorder Point (ROP) Alerts:</b> Alerts procurement managers when warehouse levels cross the reorder threshold.<br/>"
        "• <b>Economic Order Quantity (EOQ):</b> Optimizes order sizes to balance holding costs and order-setup expenses.",
        body_style
    ))
    story.append(Spacer(1, 10))

    # Compliance & Role Management
    story.append(Paragraph("3.4 Role-Based Access Control (RBAC)", h2_style))
    story.append(Paragraph(
        "The dashboard restricts capabilities based on the user's role:",
        body_style
    ))

    rbac_data = [
        [Paragraph("<b>Role</b>", table_header_style), Paragraph("<b>Privileges & Dashboard Permissions</b>", table_header_style)],
        [Paragraph("<b>Owner / Admin</b>", table_cell_bold), Paragraph("Full access. Can configure tenant settings, manage licenses, invite/delete team members, upload master datasets, override model weights, and sign off on forecasting releases.", table_cell_style)],
        [Paragraph("<b>Analyst</b>", table_cell_bold), Paragraph("Can run forecasts, generate scenarios, override promotional and discount parameters, trigger model retrain requests, and download CSV reports. Cannot modify team configurations.", table_cell_style)],
        [Paragraph("<b>Viewer</b>", table_cell_bold), Paragraph("Read-only access. Can view dashboard graphs, track forecasts, and read audit logs, but cannot edit settings, trigger forecasts, or modify data.", table_cell_style)]
    ]

    t_rbac = Table(rbac_data, colWidths=[110, 394])
    t_rbac.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    story.append(t_rbac)
    
    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)

if __name__ == "__main__":
    pdf_filename = "SANKET_Architecture_and_Flows.pdf"
    if len(sys.argv) > 1:
        pdf_filename = sys.argv[1]
    build_pdf(pdf_filename)
    print(f"Successfully generated {pdf_filename}")
