# Tenant Customization Plan

**Date:** 2026-07-26
**Author:** audit run, acting as PO / architect / BA
**Companion:** `docs/strategy/customization-summary.md` (three-minute read)
**Depends on:** `docs/audit/01`, `02`, `03`

---

## 0. The review that changed this plan

You asked me to run this through `/office-hours` and `/plan-ceo-review` and
incorporate the pushback rather than append it. Here is what the pushback was and
what it changed, so you can judge the reasoning rather than just the output.

### Office hours: the six forcing questions

**Q1. Demand reality. What evidence exists that a tenant wants this?**

None that I can find in the repository. There is no customer list, no usage
telemetry, no support thread, no sales note. More pointedly: **no tenant could
ever have paid you**, because `GET /billing/plans` returns 500 and the paywall's
every button is dead. A customization layer is a response to customers saying
"your workflow doesn't match ours." I have no evidence any customer has said
that, because I have no evidence of a customer.

*This is the single most important finding in this document.* I am not refusing
the work. I am telling you the plan below is built on an unverified premise, and
the phasing reflects that.

**Q2. Status quo. What do these users do today instead?**

This one has a real answer, and it is the strongest argument for the project.
Supply-chain planners in all five verticals run their planning in Excel, with
their own column names, their own stage names, and their own review cadence. The
workaround costs them days per cycle and does not survive the analyst leaving.
That is genuine, verifiable pain. It is also why "our tool has different words
than your tool" is a real objection and not an imagined one.

**Q3. Desperate specificity. Name the human.**

I cannot. Five verticals, zero named buyers. "Apparel companies" is a filter, not
a person. The brief asks me to build five industry templates. Building five
presets for five categories with zero named buyers in any of them is how you
spend two quarters and learn nothing. **This is why Part C recommends one
vertical, not five.**

**Q4. Narrowest wedge. What is the smallest version someone pays for this week?**

Not a customization platform. The wedge is roughly: *let a tenant rename the
things on screen to match their language, add the three fields they actually
track, and see their own logo.* That is terminology overrides plus custom fields
plus branding. It is maybe 15% of the eleven axes in your brief and probably 80%
of the felt value. **Part A is ordered so that wedge ships first and alone.**

**Q5. Observation and surprise. Has anyone been watched using this?**

Unknown to me. If the answer is no, then every field, stage name, and vocabulary
choice in Part B is my inference from domain knowledge, not from your customers.
I have labelled it as such throughout. Five hours of watching one planner would
be worth more than everything in Part B.

**Q6. Future fit. Does this matter more in three years?**

Yes, and this one holds up. Vertical SaaS is where horizontal analytics tools go
to lose. If a tenant can shape the product to their vocabulary and workflow, your
switching cost compounds and your competitors' generic dashboards look
increasingly naive. The direction is right. The sequencing is what is at issue.

### CEO review

**Premise challenge.** Is per-tenant customization the right problem right now?
Partly. The plan assumes tenants reject the product because the workflow is
fixed. The evidence says tenants cannot buy the product at all, and that a pharma
tenant is currently served the apparel archetype with a false 21 CFR Part 11
badge. **The most valuable "customization" work available today is making the
industry selection you already have actually work.** That is P0-4 in `02`, and it
is a bug fix, not a platform.

**Existing code leverage.** The brief implies greenfield. It is not:

| Axis | Already exists | Path |
|---|---|---|
| Per-tenant config row | `industry_profiles` (4 configurable fields) | `sql/002_schema.sql:173` |
| Resolution engine | `resolve_effective_config()` | `services/industry_config.py:91` |
| Open-ended config bag | `feature_flags` JSONB | `industry_config.py:121` |
| Per-tenant cache + invalidation | `ResponseCache.invalidate_tenant()` | `core/cache.py:109` |
| Design tokens for theming | CSS variables, `--accent` etc. | `frontend/tailwind.config.ts` |
| Form-field descriptor pattern | `AuthField` | `connectors/catalog.py:74` |
| Outbound extension point | webhook endpoints + delivery + retry | `routers/webhooks.py` |
| Per-industry archetypes | 5 registered contexts | `services/industry_context.py:52-165` |

Eight of the eleven axes have a foothold. This is an extension of
`resolve_effective_config`, not a new subsystem. Any plan that proposes a
parallel config service is rebuilding what you have.

**Inversion. What would make this fail?**

1. **Over-configurability.** You ship an EAV schema and a plugin runtime, every
   tenant's install becomes a snowflake, and you can no longer ship a migration
   without breaking someone. This is the named failure mode in your brief and it
   is the right thing to be afraid of.
2. **Configuring a product nobody pays for.** Twelve weeks of config work while
   `/billing/plans` still 500s.
3. **Five templates, no customers.** Effort divided by five, learning divided by
   five.
4. **Config that outruns the isolation model.** One `session_no_rls()` in the
   config resolver and tenant A reads tenant B's configuration.

**Focus as subtraction.** Your brief lists eleven axes. Shipping eleven is the
failure mode. **Part A ships four in v1, three in v2, and explicitly defers four.**

**Speed calibration.** Config *schema* is a one-way door: once tenants have data
in a shape, you own that shape forever. Config *surface* is a two-way door: you
can add an axis any time. So: think hard about storage and versioning, move fast
on which knobs to expose.

### What the review changed

| Original brief | After review |
|---|---|
| Design all 11 axes | Ship 4, then 3, defer 4. Explicit line drawn in §A.9 |
| Five industry templates | One vertical first (Apparel), sequence the rest. Part B still specs all five so you can see the shape |
| Customization as the next project | Prerequisite: one week fixing the money path first (`03` items 1-5) |
| Extension point for custom logic | **Deferred.** Webhooks are already your extension point |
| Custom objects | **Deferred.** Custom fields only in v1 |
| Configurable workflow states | **Narrowed** to labels and substages over a fixed canonical state machine |

---

# Part A. The customization architecture

## A.1 Core model: three layers, one resolver

```
  PLATFORM DEFAULT          INDUSTRY TEMPLATE            TENANT OVERRIDE
  (code, versioned          (data, shipped by us,        (data, owned by
   with the release)         per vertical)                the tenant)
        │                          │                           │
        └──────────────┬───────────┴───────────────────────────┘
                       ▼
              resolve_effective_config()
              deep merge, tenant wins,
              validated against a JSON Schema
                       ▼
            EffectiveTenantConfig  (immutable, cached)
                       ▼
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   HTTP handlers   arq workers    SPA bootstrap
                                  (GET /config/effective)
```

This extends `resolve_effective_config()` (`industry_config.py:91`), which
already does two of the three layers. The new work is the middle layer, the
schema validation, the versioning, and the cache.

**Merge semantics, stated precisely because this is where config systems rot:**

- Scalars: last writer wins (tenant > template > platform).
- Objects: deep merge by key.
- Arrays: **replace, never concatenate.** Concatenation makes it impossible for a
  tenant to remove a platform-supplied item, and it is the single most common
  source of "why is this old value still here" bugs.
- `null` is a real value meaning "explicitly unset", distinct from a missing key.

## A.2 Storage

Two mechanisms, chosen per axis by whether the data needs referential integrity.

### A.2.1 Config documents (most axes)

```sql
CREATE TYPE config_scope AS ENUM ('platform', 'industry', 'tenant');

CREATE TABLE config_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope           config_scope  NOT NULL,
    tenant_id       UUID          REFERENCES tenants(id) ON DELETE CASCADE,
    industry        industry_code,
    namespace       TEXT          NOT NULL,   -- 'terminology' | 'branding' | ...
    schema_version  INTEGER       NOT NULL,
    document        JSONB         NOT NULL,
    version         INTEGER       NOT NULL,   -- monotonic per (scope,tenant,industry,ns)
    is_published    BOOLEAN       NOT NULL DEFAULT FALSE,
    created_by      UUID          REFERENCES users(id),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    note            TEXT,

    CONSTRAINT ck_scope_shape CHECK (
        (scope = 'tenant'   AND tenant_id IS NOT NULL) OR
        (scope = 'industry' AND tenant_id IS NULL AND industry IS NOT NULL) OR
        (scope = 'platform' AND tenant_id IS NULL AND industry IS NULL)
    )
);

CREATE UNIQUE INDEX uq_config_version
  ON config_documents (scope, COALESCE(tenant_id,'00000000-0000-0000-0000-000000000000'::uuid),
                       COALESCE(industry,'fashion'), namespace, version);

CREATE UNIQUE INDEX uq_config_published
  ON config_documents (scope, COALESCE(tenant_id,'00000000-0000-0000-0000-000000000000'::uuid),
                       COALESCE(industry,'fashion'), namespace)
  WHERE is_published;

CREATE INDEX idx_config_tenant ON config_documents (tenant_id) WHERE scope = 'tenant';

ALTER TABLE config_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE config_documents FORCE  ROW LEVEL SECURITY;

-- Tenants read platform and industry rows, but only their own tenant rows.
CREATE POLICY config_documents_isolation ON config_documents
  USING (bypass_rls() OR scope <> 'tenant' OR tenant_id = current_tenant_id())
  WITH CHECK (bypass_rls() OR (scope = 'tenant' AND tenant_id = current_tenant_id()));
```

The `WITH CHECK` is deliberately narrower than the `USING`: a tenant may **read**
platform and industry documents but may only **write** its own. Without that
asymmetry a tenant admin could overwrite the industry template for everyone.

**Rows are immutable.** Editing publishes a new `version` and moves the
`is_published` flag. The partial unique index guarantees exactly one published
version per key, which makes rollback a single UPDATE and gives you a free audit
trail.

### A.2.2 Relational tables (where integrity matters)

Custom field definitions, role definitions, and notification templates get real
tables, because they are referenced by ID from other rows and JSONB gives you no
FK enforcement. Schemas in A.3, A.5, A.7.

### A.2.3 Custom field *values*: JSONB column, not EAV

```sql
ALTER TABLE products ADD COLUMN custom_fields JSONB NOT NULL DEFAULT '{}';
ALTER TABLE skus     ADD COLUMN custom_fields JSONB NOT NULL DEFAULT '{}';
CREATE INDEX idx_products_custom_fields ON products USING GIN (custom_fields jsonb_path_ops);
CREATE INDEX idx_skus_custom_fields     ON skus     USING GIN (custom_fields jsonb_path_ops);
```

**Why not EAV.** An entity-attribute-value table turns every list query into a
pivot, every filter into a self-join, and every sort into a subquery. On
`historical_sales`, which is partitioned quarterly and is your largest table,
that is a performance cliff. JSONB with a GIN index gives you containment queries
(`custom_fields @> '{"season":"AW26"}'`) at index speed, and Postgres 16's
`jsonb_path_ops` keeps the index small. The trade is that you cannot enforce
types in the database. You enforce them in the resolver instead, against the
field definitions, on write. That is the correct trade here.

**Where custom fields go:** `products`, `skus`, and `inventory_levels` in v1.
**Not** `historical_sales` or `forecast_results` in v1: those are partitioned,
high-volume, and machine-written, and adding tenant-defined JSONB to them buys
little and costs a lot.

## A.3 Axis 1: Custom fields *(v1)*

```sql
CREATE TYPE custom_field_kind AS ENUM
  ('text','number','integer','boolean','date','select','multiselect','url');

CREATE TABLE custom_field_definitions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    entity        TEXT NOT NULL,          -- 'product' | 'sku' | 'inventory_level'
    key           TEXT NOT NULL,          -- ^[a-z][a-z0-9_]{0,38}$
    label         TEXT NOT NULL,
    kind          custom_field_kind NOT NULL,
    options       JSONB NOT NULL DEFAULT '[]',   -- select / multiselect
    is_required   BOOLEAN NOT NULL DEFAULT FALSE,
    default_value JSONB,
    help_text     TEXT,
    display_order SMALLINT NOT NULL DEFAULT 0,
    is_archived   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_cfd UNIQUE (tenant_id, entity, key)
);
ALTER TABLE custom_field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_field_definitions FORCE  ROW LEVEL SECURITY;
CREATE POLICY cfd_isolation ON custom_field_definitions
  USING (bypass_rls() OR tenant_id = current_tenant_id())
  WITH CHECK (bypass_rls() OR tenant_id = current_tenant_id());
```

**Limits, enforced in code:** 40 fields per entity per tenant, key ≤ 39 chars,
50 options per select. Limits stop a tenant from turning your GIN index into a
liability, and they are far easier to raise later than to introduce later.

**Deletion is archival, never destructive.** `is_archived = true` hides the field
from forms and lists but leaves the values in `custom_fields` intact. Hard delete
is a separate, owner-only, explicitly-confirmed action that also strips the key
from every row in a background job. Silent data loss on a config change is
unacceptable.

**Type changes are forbidden.** Archive the old field, create a new one. Coercing
`text` to `number` across an unbounded JSONB column is a migration you do not
want to own.

## A.4 Axis 2: Terminology overrides *(v1)*

The highest value-per-effort axis, and the one your brief undersells. A planner
who sees "Style" instead of "Product" and "Batch" instead of "Lot" believes the
tool was built for them.

Storage: `config_documents` namespace `terminology`.

```json
{
  "schema_version": 1,
  "terms": {
    "product":        {"one": "Style",  "many": "Styles"},
    "sku":            {"one": "Colourway", "many": "Colourways"},
    "inventory":      {"one": "Stock position", "many": "Stock positions"},
    "forecast_run":   {"one": "Plan", "many": "Plans"},
    "shortage_alert": {"one": "Risk flag", "many": "Risk flags"}
  }
}
```

**The real cost is not the backend, it is the frontend.** Today every noun is a
literal in TSX. You need a token layer: `t('product.one')` instead of
`"Product"`. That is a mechanical but wide change across
`frontend/src/pages/` and `frontend/src/components/`. Budget it honestly. It is
the largest single line item in v1 and it is worth it, because it is also the
prerequisite for ever localising the product.

**Governed vocabulary, not free text.** Tenants override a fixed key set that we
publish. They cannot invent new terms. This keeps the SPA's token map finite and
means a missing override falls back cleanly instead of rendering a blank.

## A.5 Axis 3: Branding and white-label *(v1)*

Cheapest axis with the highest perceived value, because the design-token system
already exists.

`config_documents` namespace `branding`:

```json
{"schema_version": 1,
 "display_name": "Northwind Apparel",
 "logo_url": "https://cdn.../t/<tenant>/logo.svg",
 "accent": "#0F766E",
 "accent_fg": "#FFFFFF",
 "login_subtitle": "Merchandise planning"}
```

Served in the SPA bootstrap and written to the existing CSS variables. No new
theming machinery.

**Security, non-negotiable:**
- Colours validated against `^#[0-9a-fA-F]{6}$`. Never interpolate a tenant string
  into a `<style>` block without that check, or you have CSS injection.
- Logos uploaded to your own object storage and re-served from your CDN. Never
  render a tenant-supplied arbitrary URL, or you have an SSRF and a tracking
  vector.
- No custom CSS, no custom HTML, no custom fonts by URL in v1. That is the
  white-label line.

## A.6 Axis 4: Configurable dashboards *(v1, narrow)*

**Widgets are code. Layout is data.** We publish a registry of widget types with
declared props. A tenant arranges them.

```json
{"schema_version": 1,
 "dashboards": [{
   "id": "default", "name": "Weekly plan review",
   "layout": [
     {"widget": "shortage_alerts", "w": 6, "h": 4, "props": {"severity_min": "high"}},
     {"widget": "forecast_accuracy", "w": 6, "h": 4, "props": {"window_weeks": 13}},
     {"widget": "inventory_coverage", "w": 12, "h": 5, "props": {}}
   ]}]}
```

Unknown widget ids render an "unavailable" tile rather than crashing the page.
Props are validated against the widget's declared schema at publish time and
again at render time.

**Not in v1:** a query builder, custom SQL, user-defined metrics. That is a
reporting product and it is a different company.

## A.7 v2 axes

### A.7.1 Workflow stage labels and substages

The constraint: you have **16 Postgres ENUMs** (`sql/002_schema.sql:8-63`,
`005:40-152`, `006:8-39`). `alert_status`, `gxp_batch_status`, `product_status`
and the rest are compile-time contracts that the ML layer, the alert engine, and
the audit trail all depend on. Letting tenants define arbitrary state machines
over those is how you make the product unmaintainable.

**The line:** the canonical state machine stays in code. Tenants get two things.

1. **Labels.** Namespace `workflow`, mapping canonical state → tenant label.
   `{"gxp_batch_status": {"quarantined": "Under QA hold"}}`. Pure presentation.
2. **Substages.** A nullable `substage TEXT` column on the relevant entities plus
   a tenant-defined ordered list per canonical state. Substages are advisory:
   they drive UI grouping and reporting, and **no platform logic branches on
   them**. That last clause is the whole safety property.

If a tenant genuinely needs a different state machine, that is a product
decision that becomes a new canonical state in a release, not configuration.

### A.7.2 Role and permission templates

Keep `owner / admin / analyst / viewer` as the permission **primitives**. Add:

```sql
CREATE TABLE role_definitions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key          TEXT NOT NULL,
    label        TEXT NOT NULL,           -- "Demand Planner"
    base_role    user_role NOT NULL,      -- ceiling: cannot exceed this
    capabilities TEXT[] NOT NULL DEFAULT '{}',
    CONSTRAINT uq_role_def UNIQUE (tenant_id, key)
);
```

`capabilities` are drawn from a **fixed, code-defined enumeration**
(`forecast.run`, `inventory.write`, `billing.manage`, …). A tenant role can only
ever be a *subset* of `base_role`. Privilege escalation by configuration is
structurally impossible, which is the only acceptable design given that
`rbac.py` currently fails closed and should keep doing so.

### A.7.3 Notification and template editing

```sql
CREATE TABLE notification_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_key   TEXT NOT NULL,       -- 'shortage_alert.raised'
    channel     TEXT NOT NULL,       -- 'email' | 'webhook' | 'in_app'
    subject     TEXT,
    body        TEXT NOT NULL,
    is_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_notif UNIQUE (tenant_id, event_key, channel)
);
```

Rendering uses a **logic-less** templating dialect (Mustache-style) with an
allowlisted variable set per `event_key`, rendered in a sandbox with a hard
timeout, HTML-escaped by default. No Jinja, no arbitrary expressions, no loops
over unbounded collections. Server-side template injection is a top-tier
vulnerability class and a template editor is exactly how you invite it.

## A.8 Industry-specific billing rules *(v2)*

The brief asks for per-vertical pricing. The honest answer is that this is mostly
a `plans` extension, not a pricing engine.

```sql
ALTER TABLE plans ADD COLUMN pricing_model TEXT NOT NULL DEFAULT 'flat';
   -- 'flat' | 'per_seat' | 'per_location' | 'usage' | 'annual_contract'
ALTER TABLE plans ADD COLUMN industry_availability industry_code[] NOT NULL DEFAULT '{}';
   -- empty array = available to all
ALTER TABLE plans ADD COLUMN min_commitment_months SMALLINT NOT NULL DEFAULT 0;
```

`usage_events` and `usage_rollups_daily` already exist
(`sql/005_phase5_realtime_billing.sql:102,140`) with a `meter_kind` enum that
includes `user_seat` and `active_sku`. Per-seat and usage pricing are largely a
matter of wiring the meters you have into invoice generation, which does not
exist yet (`03`, item 7).

**Do not build a pricing DSL.** Five pricing models covers all five verticals.
Enterprise contracts stay out-of-band, which is what
`start_subscription`'s zero-cost branch (`subscription_manager.py:171-195`)
already assumes.

## A.9 The line: configurable data vs. code

You asked to be told explicitly where to stop. Over-configurability is the named
failure mode, so this table is the most important one in the document.

| Configurable data | Stays code | Why |
|---|---|---|
| Labels, terminology, pluralisation | The entity model itself | Renaming `Product` to `Style` is presentation. Adding a real new entity is a schema and a migration. |
| Custom fields on 3 entities | Custom *objects* | An object needs list views, permissions, forecasting semantics, and an API. That is a platform, not a field. |
| Workflow stage labels + advisory substages | The canonical state machine | 16 ENUMs are contracts with the ML layer and the audit trail. Branching platform logic on tenant-defined states is unmaintainable. |
| Role labels + capability subsets | The capability enumeration | Tenants compose permissions. They never invent them. Escalation-by-config must be structurally impossible. |
| Dashboard layout, widget props | Widget implementations | Layout is arrangement. Widgets are code with tests. |
| Notification copy + enable/disable | The event taxonomy and delivery | Tenants write the words. They do not define when the system fires. |
| Branding tokens (colour, logo, name) | CSS, fonts, HTML | Custom CSS is a persistent XSS vector and an unbounded support burden. |
| Forecast horizon, signal types, service level | Model selection and training | Config picks parameters. It never picks code paths in the ML stack. |
| Plan pricing model, industry availability | The billing state machine | Five models is enough. A pricing DSL is a product. |
| **Deferred entirely in v1 and v2** | | |
| Custom objects | | Ship custom fields, watch what tenants actually stuff into them for two quarters, then decide. |
| Custom forms | | Forms fall out of custom field definitions plus display order. A form builder is a separate product. |
| Scripting / plugin runtime | | **Webhooks already are your extension point** (`routers/webhooks.py`). Outbound events plus a documented ingest API covers the real integration need without you operating a sandbox. Revisit only when a paying customer names a use case webhooks cannot serve. |
| Per-tenant custom integrations | | Finish the four connectors you have before adding a fifth. The catalogue already overclaims (`02`, P2-7). |

## A.10 Resolution, caching, performance

```
request
   │
   ├─ TenantContextMiddleware  → tenant_id, industry, role      [exists]
   │
   ├─ get_effective_config(tenant_id, industry)
   │     │
   │     ├─ Redis GET  cfg:v{config_version}:{tenant}:{industry}   ← hit: ~1ms
   │     │
   │     └─ miss: 1 query for all published documents in
   │              (platform, industry, tenant) scope
   │              → validate → merge → freeze → SETEX 1h
   │
   └─ handler receives an immutable EffectiveTenantConfig
```

**One query, not one per namespace.** All published documents for the three
scopes come back in a single `SELECT ... WHERE is_published` with an `IN` over
scopes. Merging happens in Python. Roughly 8 to 15 rows.

**Invalidation is a version bump, not a delete.** `tenants.config_version`
increments on every publish. The cache key contains it, so old entries expire
naturally and there is no thundering-herd delete across replicas. This mirrors
the pattern `ResponseCache._version_key` (`core/cache.py:53`) already uses.

**Budget:** resolution must add < 5ms p99 on a cache hit and < 40ms on a miss.
Add a Prometheus histogram `config_resolve_seconds` and a
`config_cache_hit_ratio` gauge. Alert if hit ratio drops below 0.9, which is your
early warning that something is bumping `config_version` in a loop.

**Isolation, stated explicitly because it is the one way this feature could
compromise the platform:** `get_effective_config` uses `Database.session(tenant_id)`.
It must **never** use `session_no_rls()`. Add a test that asserts tenant A's
resolver cannot observe tenant B's documents, in the style of
`tests/test_rls_isolation.py`. Cache keys are tenant-scoped and must be
constructed from `request.state.tenant_id`, never from any client-supplied value.

## A.11 Versioning, migration, upgrade safety

Every document carries `schema_version`. Every namespace registers a migration
chain in code:

```python
CONFIG_MIGRATIONS = {
  "terminology": {1: _terminology_v1_to_v2},
  "branding":    {},
}
```

Rules that keep this from becoming a maintenance trap:

1. **Migrate on read, persist lazily.** A document at `schema_version=1` is
   upgraded in memory on resolution. It is rewritten to the table by a background
   job, not on the request path. Reads never block on a migration.
2. **Never drop unknown keys.** An older replica mid-rollout must not destroy
   config it does not understand. Preserve and pass through.
3. **Additive by default.** New keys ship with a platform default so existing
   tenant documents stay valid without being touched.
4. **Removing a key is a two-release job.** Release N stops reading it. Release
   N+1 drops it. Never both.
5. **Rollback is a pointer move.** Because rows are immutable and `is_published`
   is a flag, "revert to version 4" is one UPDATE. Expose it in the admin UI as
   version history with a diff and a Restore button.
6. **Template updates never silently overwrite tenants.** When you ship a new
   version of an industry template, tenants on the old version see a
   "Template update available" prompt with a diff. Applying it is their choice.
   Auto-applying template changes to live tenants is how you break someone's
   Monday.

**Deployment interaction:** config schema changes and code changes are deployed
independently and can be out of order. Every migration must be forward and
backward tolerant for one release. Given `02`'s finding that your running build
was five days behind `main`, this is not hypothetical.

## A.12 API surface

```
GET    /api/v1/config/effective                 → resolved config for the SPA bootstrap
                                                  (any authenticated member)

GET    /api/v1/config/{namespace}               → published tenant document
PUT    /api/v1/config/{namespace}               → publish a new version   [admin]
GET    /api/v1/config/{namespace}/versions      → history                 [admin]
POST   /api/v1/config/{namespace}/restore/{v}   → roll back               [admin]
POST   /api/v1/config/{namespace}/preview       → validate + merge, no write [admin]

GET    /api/v1/custom-fields?entity=product     → definitions
POST   /api/v1/custom-fields                    → create                  [admin]
PATCH  /api/v1/custom-fields/{id}               → label/order/required    [admin]
POST   /api/v1/custom-fields/{id}/archive       → soft delete             [admin]

GET    /api/v1/industry-templates               → catalogue
POST   /api/v1/industry-templates/{key}/apply   → apply preset            [owner]
GET    /api/v1/industry-templates/{key}/diff    → what applying changes   [admin]
```

All mutations use `require_admin_db` (`rbac.py:158`), the DB-rechecking variant,
because configuration changes are tenant-wide and a demoted admin should not
retain them. Template application is `require_owner_db`.

Every mutation writes to `audit_log`. Configuration changes are exactly the kind
of thing that gets asked about during a GxP audit, and you already have the
table.

## A.13 Admin UI

New section under `/workspace/settings`, admin-only:

```
Settings
├── Workspace          name, industry, region                [exists]
├── Customization                                            [NEW]
│   ├── Vocabulary     side-by-side default vs yours, live preview
│   ├── Fields         per entity, drag to reorder, type picker, archive
│   ├── Branding       logo upload, accent picker w/ contrast check, preview
│   ├── Dashboards     drag-and-drop over the widget registry
│   └── History        version list, diff, Restore
├── Team               members, roles, invites               [exists]
├── Integrations                                             [exists]
└── Billing                                                  [exists]
```

Three UI principles that matter more than the layout:

- **Preview before publish.** Every editor shows the resolved result against real
  tenant data before the Publish button does anything. `POST /config/{ns}/preview`
  exists for this.
- **Show the inheritance.** Each field displays where its current value came
  from: Platform default, Industry template, or Your override. A "Reset to
  template" control per field. Config systems become unusable when users cannot
  tell what they changed.
- **Contrast checking on the accent picker.** You have an accessibility skill and
  no WCAG pass. Do not ship a colour picker that lets a tenant configure
  unreadable text.

---

# Part B. The five verticals

**Provenance warning.** Everything in Part B is my domain inference, cross-checked
against `services/industry_context.py:52-165` and the per-industry routers. It is
**not** validated against your customers, because office-hours Q5 has no answer.
Treat every field list and stage name as a hypothesis to test in a customer
conversation, not a specification to build from. Five hours with one real planner
would change more of this than another day of my analysis.

## B.1 Apparel & Fashion

**Code today:** `industry_context.py:52`, horizon 26wk, signals
trend_search / social_sentiment / weather / competitor_price. Feature flags
`markdown_optimizer`, `assortment_planning`. Router
`routers/industries/fashion.py`.

**Jobs to be done.** Decide the buy quantity per style/colour/size before the
season, months ahead of demand signal. Decide when to mark down, and by how much,
before the season ends and the stock is worthless. Allocate limited stock across
channels and doors.

**Vocabulary.** Style (not Product). Colourway. Size curve. SKU = style-colour-size.
Option count. OTB (open to buy). Sell-through %. Markdown cadence. Season codes
(SS26, AW26). Drop. Range plan. Door. Full-price sell-through.

**Workflow stages.** Range planning → OTB sign-off → Buy committed → In production
→ In transit → Landed → In season → Markdown → Terminal / carryover.

**Fields and objects.** Season, drop number, size curve, option count, cost price,
first landed date, markdown tier, channel, door group, fabric/composition,
sustainability flag.

**Compliance.** Light. Country-of-origin labelling, EU Digital Product Passport
becoming relevant for textiles. Not GxP-grade.

**Billing expectation.** Per-seat, monthly, with SKU-count tiers. Merch teams are
small (5 to 25 planners), buy fast, and expect self-serve. Highest fit with the
plans you already have.

**Preset bundle.** Horizon 26wk. Terminology map above. Custom fields: season,
drop, size_curve, cost_price, markdown_tier. Dashboard: sell-through, markdown
exposure, OTB remaining, shortage alerts. Signals: trend_search, social_sentiment,
weather, competitor_price. Roles: Merchandiser (analyst), Buyer (admin),
Allocator (analyst).

## B.2 Consumer Electronics

**Code today:** `industry_context.py:77`, horizon 12wk (shortest). Router
`routers/industries/electronics.py`.

**Jobs to be done.** Manage short product lifecycles against long component lead
times. Avoid being caught with obsolete inventory at end-of-life. Plan NPI ramp
and EOL run-down. Track component and allocation risk.

**Vocabulary.** SKU / model / config. BOM. Component. Allocation. Lead time.
Attach rate. NPI. EOL. Sell-in vs sell-through. Channel inventory. Price
protection. Refurb / RMA.

**Workflow stages.** NPI → Ramp → Volume → Mature → EOL announced → Last time buy
→ Run-down → Discontinued.

**Fields and objects.** Model number, BOM revision, component criticality, lead
time days, lifecycle stage, attach-rate parent, warranty period, channel,
allocation %, last-time-buy date.

**Compliance.** WEEE, RoHS, CE/FCC. Battery regulations. Meaningful but
documentation-level, not process-validated.

**Billing expectation.** Per-seat with usage overage on forecast volume. Larger
buying committees, quarterly cycles, expect a pilot before contract.

**Preset bundle.** Horizon 12wk. Custom fields: model_number, lifecycle_stage,
lead_time_days, bom_revision, attach_rate_parent. Dashboard: component risk,
lifecycle mix, channel inventory, EOL exposure. Roles: Supply Planner, Product
Manager, Channel Manager.

## B.3 Pharmaceuticals

**Code today:** `industry_context.py:102`, horizon 52wk (longest), audit level
GxP. Real scaffolding exists: `pharma_batches` table (`sql/002_schema.sql:325`),
`gxp_batch_status` enum (`:63`), `models/pharma.py`, `tests/test_pharma_gxp.py`,
`routers/industries/pharma.py`. **Blocked by `02` P0-4: this archetype is not
actually applied at runtime today.**

**Jobs to be done.** Forecast against long, validated manufacturing lead times.
Manage batch expiry and shelf life so stock does not die on the shelf. Never
stock out on a critical or life-sustaining product. Survive an audit with an
intact record.

**Vocabulary.** Batch / lot (not "inventory unit"). Molecule. Formulation.
Strength. Pack size. Shelf life. Expiry. Quarantine. QA release. Recall.
Cold chain. NDC / marketing authorisation. Serialisation.

**Workflow stages.** Planned → In production → Quarantined → QA release → Released
→ Distributed → Expiring → Expired / recalled. This maps onto the existing
`gxp_batch_status` enum, which is exactly why A.7.1 keeps the canonical machine
in code.

**Fields and objects.** Batch number, manufacture date, expiry date, shelf life
days, storage condition, QA release date and signatory, molecule, strength, pack
size, licence number, serialisation range.

**Compliance. This is the differentiating constraint and it changes the
architecture.** 21 CFR Part 11 and EU Annex 11 require: attributable, legible,
contemporaneous, original, accurate records (ALCOA+); electronic signatures with
meaning and intent; immutable audit trails; and **computer system validation** of
the software itself.

Three concrete consequences for the customization layer:

1. Every config change must be in the audit trail with actor, timestamp, before
   and after. A.12 already mandates this; for pharma it is a legal requirement,
   not hygiene.
2. **Config changes may need e-signature.** A validated system where an admin can
   silently change a workflow label that appears on a batch record is a finding.
   Pharma tenants likely need a second-person approval step on config publish.
   *This is the one place I would extend the architecture per-vertical:* an
   `approval_required` flag on `config_documents` with a second signatory.
3. **Configurability itself is a validation burden.** Every configurable path is a
   path the customer must validate. Fewer knobs is a feature for this vertical,
   not a limitation. Do not lead with customization when selling to pharma.

**Billing expectation.** Annual contract, invoiced, procurement-led, 6 to 12 month
sales cycle, security review and often a quality agreement. Per-seat is
secondary. `min_commitment_months` in A.8 exists for this.

**Preset bundle.** Horizon 52wk. GxP audit level actually enforced. Custom fields:
batch_number, expiry_date, storage_condition, molecule, strength, qa_release_by.
Approval-required config changes. Dashboard: expiry exposure, batch status,
critical-product coverage, audit trail. Roles: Demand Planner, QA (approve-only),
Regulatory (read + export).

## B.4 Agro / Farm Inputs

**Code today:** `industry_context.py:131`, horizon 26wk. Router
`routers/industries/agrocenter.py`, `sql/007_agrocenter.sql`.

**Jobs to be done.** Forecast demand that is driven by weather and the crop
calendar rather than by consumer trend. Position stock regionally before a season
that lasts weeks. Manage products with real shelf life and regulated handling.

**Vocabulary.** Input (seed, fertiliser, crop protection). Active ingredient.
Crop. Season (Kharif / Rabi / Zaid in India). Acreage. Dealer / retailer.
Depot. Agronomic window. Application rate. Batch and expiry.

**Workflow stages.** Pre-season forecast → Dealer indent → Allocation → Dispatched
to depot → At dealer → Sold through → Season close → Carry-over.

**Fields and objects.** Crop, active ingredient, concentration, pack size,
application rate, season code, region / agro-climatic zone, dealer tier, depot,
expiry, licence number.

**Compliance.** Pesticide registration (CIB&RC in India), label claims, restricted
products, batch traceability. Real but lighter than pharma.

**Billing expectation.** **Per-location, not per-seat.** This vertical is
distributed across depots and dealer networks, and seat counts do not track value.
Strongly seasonal, so annual contracts are preferable to monthly. This is the
clearest case for `pricing_model = 'per_location'` in A.8.

**Preset bundle.** Horizon 26wk aligned to the crop calendar. Custom fields: crop,
active_ingredient, season_code, region_zone, dealer_tier, expiry_date. Weather
signal weighted heavily. Dashboard: regional coverage, season burn-down, dealer
stock, expiry risk. Roles: Regional Manager, Depot Planner, Dealer (limited view).

## B.5 Hardware & Industrial Supply

**Code today:** `industry_context.py:165`, horizon 16wk. Router
`routers/industries/hardware.py`, `sql/008_b_hardware.sql`.

**Jobs to be done.** Manage very large, slow-moving, long-tail catalogues where
most SKUs sell in single digits per year. Hit service-level targets on
maintenance-critical parts. Balance carrying cost against stockout cost across
many branches.

**Vocabulary.** Part / item (not "product"). Part number. Fitment. Substitute /
supersession. Branch. Bin. Min-max. Reorder point. Fill rate. Non-stock / special
order. Kit / assembly.

**Workflow stages.** Catalogued → Stocked → Reorder point hit → On order →
Received → Allocated → Slow-moving → Obsolete / superseded.

**Fields and objects.** Part number, manufacturer part number, supersedes /
superseded-by, fitment reference, branch, bin location, min qty, max qty, reorder
point, unit of measure, hazmat class, supplier lead time.

**Compliance.** Hazmat handling and transport classification. Certification
records for safety-critical parts. Modest.

**Billing expectation.** Per-location (branch) with SKU-count tiers. Long-tail
catalogues mean `active_sku` metering matters more here than anywhere else, and
you already have that meter (`models/billing.py:31`).

**Preset bundle.** Horizon 16wk. Custom fields: part_number, mfr_part_number,
supersedes, branch, bin_location, min_qty, max_qty, uom. Dashboard: fill rate by
branch, slow-moving capital, reorder queue, supersession exposure. Roles: Branch
Manager, Purchasing, Counter Staff (read).

## B.6 What is genuinely shared vs. genuinely different

The most useful output of Part B.

| Dimension | Shared | Different |
|---|---|---|
| Forecast horizon | mechanism | 12 / 16 / 26 / 26 / 52 weeks |
| Demand drivers | signal pipeline | trend vs lifecycle vs epidemiology vs weather vs maintenance |
| Expiry / shelf life | — | **Critical** in pharma and agro, absent in hardware and electronics |
| Lifecycle management | — | **Critical** in electronics (EOL), absent in hardware |
| Location dimension | — | **Critical** in agro and hardware, weak in apparel and pharma |
| Seasonality shape | — | Sharp in apparel and agro, flat in pharma and hardware |
| Compliance depth | audit_log | Pharma is a different order of magnitude |
| Billing model | plans + meters | per-seat vs per-location vs annual contract |
| Vocabulary | token layer | Completely different in all five |

**The insight for Part C:** the axes that recur across verticals are terminology,
custom fields, and dashboards. Those are exactly the three in v1. Expiry,
lifecycle and location are each needed by only two of five, which makes them
per-vertical features rather than platform axes, and means they should be built
as first-class code for the vertical that needs them rather than configured.

---

# Part C. Build plan

## C.0 Prerequisite: one week fixing the money path

**Do not start C.1 until `03` items 1 through 5 are done.** Restart the backend,
fix the `/billing/plans` 500, add server-side entitlement, fix the onboarding and
industry session bugs, strip passwords from error bodies.

Reasoning, from the CEO review's inversion instinct: the worst outcome here is
twelve weeks of configuration work on a product that still cannot take money and
is still free to anyone with devtools. Item 4 on that list is also literally the
first customization feature, since it makes the industry archetype you already
built actually apply.

Roughly one week agent-assisted.

## C.1 Shared infrastructure vs. per-vertical

**Shared (build once):** config document store and versioning; the resolver, cache
and invalidation; JSON Schema validation; custom field definitions plus JSONB
columns and GIN indexes; the frontend terminology token layer; branding tokens;
the dashboard widget registry; the config admin UI; the template apply/diff
mechanism; audit-log integration.

**Per-vertical (repeat five times, cheap once shared exists):** the template
document itself (terminology, fields, dashboard, signals, horizon, roles); seed
data and a demo dataset; sales collateral.

**Per-vertical code (not configuration, do not pretend otherwise):** expiry and
shelf-life logic for pharma and agro; lifecycle and EOL logic for electronics;
multi-location min-max and supersession for hardware; markdown optimisation for
apparel. These are B.6's "different" rows. Trying to express them as
configuration is the over-configurability trap.

## C.2 Which vertical first: Apparel & Fashion

**Recommendation: Apparel & Fashion.** Not pharma, despite pharma having the
highest contract value and the most existing scaffolding.

**Why apparel:**

1. **Your only two working integrations are Shopify and WooCommerce**
   (`services/integrations/`). Both are retail commerce platforms. An apparel
   tenant can connect a real data source on day one. A pharma tenant cannot,
   because you have no ERP or SAP connector, and pharma does not run on Shopify.
   Time-to-value is the whole game for the first vertical.
2. **Self-serve fits.** Merch teams are small, buy monthly, and do not require a
   security review. That matches the billing you already have once it works.
3. **Fastest learning loop.** You need answers to office-hours Q1 and Q5. Apparel
   gives you a customer in weeks, not two quarters.
4. **Cheapest to be wrong.** If the customization axes are wrong, an apparel
   tenant tells you in a week. A pharma tenant tells you after a six-month
   procurement cycle.

**Why not pharma first,** even though it is tempting: you currently ship a false
21 CFR Part 11 claim (`02` P0-4). Selling into pharma before that is fixed and the
GxP path is genuinely validated is a trust risk you cannot buy back.
Pharma also needs e-signature on config changes (B.3), an ERP connector, and CSV
documentation. It is the highest-value vertical and it should be second, not
first, and only once the compliance claim is real.

**Sequence:** Apparel → Hardware → Electronics → Agro → Pharma.

Hardware second because per-location and `active_sku` metering are shared with
agro, so building them once serves two verticals. Pharma last because it needs the
most net-new platform work (e-signature, validation, ERP) and carries the most
risk if rushed.

## C.3 Phasing

### Phase 0 — Money path *(1 week, agent-assisted)*
`03` items 1-5. Gate: a test tenant can subscribe, and a cancelled tenant gets 403
from `/api/v1/products`.

### Phase 1 — Config foundation *(2-3 weeks)*
`config_documents`, RLS + FORCE RLS, resolver, Redis cache, JSON Schema
validation, versioning and rollback, audit-log wiring, `GET /config/effective`.
No user-visible feature. **Ship branding as the first namespace** so Phase 1 has
something demonstrable rather than being pure plumbing.
**Risk:** invisible work slips. Mitigate by shipping branding inside this phase.
**Gate:** RLS isolation test for config passes; p99 resolve < 5ms cached.

### Phase 2 — Terminology *(2-3 weeks)*
The frontend token layer. Widest diff in the project. Extract every user-facing
noun from TSX to `t()` keys, publish the governed key set, build the Vocabulary
editor with live preview.
**Risk:** the diff touches nearly every page, and you have three frontend tests.
Mitigate by adding Playwright coverage on the top five pages **before** starting,
and by doing the extraction one page at a time behind a flag.
**Gate:** every page renders correctly with an override map applied and with an
empty one.

### Phase 3 — Custom fields *(2-3 weeks)*
Definitions table, JSONB columns, GIN indexes, write-path validation, admin
editor, list/detail rendering, CSV import mapping to custom fields.
**Risk:** query performance on `products` and `skus` under GIN. Mitigate with a
load test at 100k SKUs before shipping, and the 40-field cap.
**Gate:** filtered list query on a custom field stays under 200ms p99 at 100k SKUs.

### Phase 4 — Apparel template + first design partner *(2 weeks)*
Assemble the preset from B.1. Apply/diff mechanism. Demo dataset. **Put it in
front of a real apparel planner and watch them use it without helping.** That is
office-hours Q5, and it is the actual deliverable of this phase.
**Gate:** one named tenant live on the template. Not "template shipped."

### Phase 5 — Dashboards *(2-3 weeks)*
Widget registry, layout config, drag-and-drop editor, unknown-widget fallback.
**Defer if Phase 4 says tenants do not care.** This is the axis most likely to be
cut, and cutting it is fine.

### Phase 6 — v2 axes *(sequenced by demand, not by plan)*
Workflow labels and substages, role templates, notification templates, per-vertical
billing models. **Build the one a paying customer has asked for. Not all four.**

### Phases 7+ — Remaining verticals
Hardware, Electronics, Agro, Pharma, in that order, each ~2 weeks of template work
plus its per-vertical code from C.1.

**Total to a customer live on a customized vertical: roughly 11 to 14 weeks
agent-assisted**, of which the first is bug fixing and the last two are a real
customer rather than a feature.

## C.4 Build vs. defer

**Build now:** config store, resolver, cache, versioning, custom fields,
terminology, branding, apparel template, admin UI, audit integration.

**Build when a customer asks:** dashboards, workflow labels, role templates,
notification templates, per-vertical billing models.

**Defer, with a stated trigger:**

| Deferred | Revisit when |
|---|---|
| Custom objects | Two paying tenants have hit the 40-field cap and can name the object |
| Custom forms | The field editor's display-order control is demonstrably insufficient |
| Scripting / plugin runtime | A paying customer names a use case webhooks cannot serve |
| Per-tenant integrations | The four existing connectors are solid and the catalogue no longer overclaims |
| Config marketplace | You have more than 20 tenants on templates |

## C.5 Risks

| Risk | Phase | Severity | Mitigation |
|---|---|---|---|
| Configuring a product that cannot take money | 0 | **Critical** | Phase 0 gates everything |
| Zero validated demand for customization | all | **Critical** | Phase 4 is a design partner, not a feature. Kill or pivot on that signal |
| Terminology refactor destabilises the SPA | 2 | High | Playwright coverage first, page-by-page behind a flag |
| Over-configurability creep | all | High | §A.9 is the contract. Any new axis requires a named paying customer |
| GIN index performance on custom fields | 3 | Medium | Load test at 100k SKUs, 40-field cap, no custom fields on partitioned tables |
| Config change breaks a tenant with no rollback | 1 | Medium | Immutable versions, `is_published` pointer, Restore in the UI |
| Template update overwrites tenant customization | 4+ | Medium | Opt-in with a diff. Never auto-apply |
| Config bypasses RLS | 1 | **Critical** | Never `session_no_rls()` in the resolver. Explicit isolation test |
| Template injection via notification editor | 6 | High | Logic-less dialect, allowlisted variables, sandboxed, escaped by default |
| Pharma config changes without e-signature | 7+ | High | `approval_required` on config publish for GxP tenants |
| Building five templates before one customer | all | High | C.2 sequencing. One vertical, then decide |

## C.6 How you will know this was worth building

State these before you start, so the answer is not retrofitted:

- **Leading:** % of tenants that publish at least one config change in their first
  30 days. Below 20% means the axes are wrong.
- **Which axes get used.** If terminology is used 10x more than dashboards, cut
  dashboards. Instrument this from Phase 1.
- **Lagging:** time-to-first-forecast for a tenant on a template vs. without.
  That is the actual claim the templates make.
- **Retention delta** between tenants who customized and those who did not, once
  n is meaningful.
- **Counter-metric:** support tickets mentioning configuration. If this rises
  faster than adoption, you have shipped complexity rather than capability.
