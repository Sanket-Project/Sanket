# Tenant Customization — Executive Summary

**Three-minute read. Full plan: `customization-plan.md`.**

---

## The headline

The direction is right. The sequencing in the brief is not.

You asked for eleven customization axes across five industries. I am recommending
**four axes, one industry, and one week of bug fixing first**. The reasoning is
below, and the full plan still specs all five verticals so you can see the shape.

---

## Three things that changed my answer

**1. You cannot currently take money.** `GET /billing/plans` returns 500 on your
running backend. Every button on the paywall is dead. Separately, the paywall is a
React component with nothing behind it, so `/api/v1/products`, `/skus`,
`/inventory/levels` and the rest all return 200 with no subscription at all. The
product is simultaneously unbuyable and free. Twelve weeks of configuration work
on top of that is the wrong bet.

Related, and worse: **462 lines of payment security fixes are sitting
uncommitted** in your working tree. `HEAD` still has the vulnerable
caller-supplied `trial_days`. Your image build runs off the committed tree, so
those fixes cannot reach staging or production no matter how many times you
deploy. Commit them first.

**2. There is no evidence a tenant wants this.** No customer list, no telemetry,
no support thread naming customization as the blocker. And no tenant could have
paid you, because of point 1. The premise may well be right, but it is unverified,
and the plan should be shaped to test it cheaply rather than to bet twelve weeks
on it.

**3. The customization you already built does not work.** A tenant who selects
Pharmaceuticals is served the Apparel archetype at runtime: 26-week horizon
instead of 52, wrong signals, wrong feature flags, and standard audit instead of
GxP, while the UI displays a `21 CFR PART 11` badge. Fixing that is the highest
value "customization" work available today, and it is a bug fix, not a platform.

---

## What to build

**Ship in v1 (four axes):**

| Axis | Why first |
|---|---|
| **Terminology overrides** | Highest value per unit effort. "Style" not "Product" is what makes a planner believe the tool was built for them |
| **Custom fields** | Three entities, JSONB + GIN index, 40-field cap. Not EAV |
| **Branding** | Cheapest axis. Your design-token system already exists |
| **Dashboard layout** | Widgets are code, layout is data. Cut this if v1 says nobody uses it |

**Ship in v2 when a customer asks:** workflow stage labels, role templates,
notification templates, per-vertical billing models.

**Defer with a stated trigger:** custom objects, custom forms, scripting/plugin
runtime, per-tenant integrations.

**Where the line sits.** Labels are data, the entity model is code. Custom fields
are data, custom objects are code. Stage *labels* are data, the state machine
stays code (you have 16 Postgres ENUMs that the ML layer and audit trail depend
on). Tenants compose permissions from a fixed capability list; they never invent
permissions. And **webhooks are already your extension point** — you do not need
to operate a scripting sandbox.

---

## Which industry first: Apparel & Fashion

Not pharma, despite pharma having the highest contract value.

**Because your only two working integrations are Shopify and WooCommerce.** An
apparel tenant connects real data on day one. A pharma tenant cannot, because you
have no ERP connector and pharma does not run on Shopify. Apparel also buys
self-serve in weeks, where pharma takes two quarters and a security review, which
means apparel answers "does anyone want this?" far faster.

**Pharma should be last, not second.** It needs e-signature on config changes, an
ERP connector, computer system validation, and a compliance claim that is actually
true. It is the biggest prize and the biggest risk if rushed.

**Sequence:** Apparel → Hardware → Electronics → Agro → Pharma.
Hardware second because per-location pricing and SKU metering are shared with
Agro, so you build them once and serve two.

---

## Timeline

| Phase | What | Duration |
|---|---|---|
| 0 | **Money path.** Restart backend, fix `/billing/plans` 500, server-side entitlement, fix onboarding + industry bugs | 1 wk |
| 1 | Config store, resolver, cache, versioning. Ship branding inside it | 2-3 wks |
| 2 | Terminology token layer (widest diff in the project) | 2-3 wks |
| 3 | Custom fields | 2-3 wks |
| 4 | Apparel template **+ one real design partner using it unaided** | 2 wks |
| 5 | Dashboards (cut if Phase 4 says no) | 2-3 wks |
| 6+ | v2 axes and remaining verticals, demand-driven | ongoing |

**~11-14 weeks agent-assisted** to a named customer live on a customized vertical.
Phase 4's deliverable is a customer, not a feature.

---

## The four risks that matter

1. **Configuring a product nobody can buy.** Phase 0 gates everything.
2. **Zero validated demand.** Phase 4 is a design partner, not a launch. Be
   willing to kill the roadmap on that signal.
3. **Over-configurability.** The line in §A.9 of the full plan is a contract. Any
   new axis requires a named paying customer.
4. **Config bypassing tenant isolation.** The resolver must never use
   `session_no_rls()`. One explicit isolation test, in the style of the one you
   already have.

---

## The one decision I need from you

**Do you have a customer, a pipeline, or a pilot in any of the five verticals?**

If yes, that overrides my Apparel recommendation entirely. Build for the customer
you have.

If no, then Phase 4 is the most important two weeks in this plan, and everything
before it exists to make those two weeks possible.
