# 00 — Open Questions

Running list of things I need from you. Updated as the audit proceeds.

---

## Resolved

| # | Question | Answer | Date |
|---|---|---|---|
| Q1 | Which five industries? | Apparel & Fashion, Consumer Electronics, Pharmaceuticals, Agro, Hardware — matches the five `IndustryCode` values already in `app/models/enums.py`. | 2026-07-26 |
| Q2 | Which environment for Phase 2? | `http://localhost:5173`, driven via Chrome. | 2026-07-26 |
| Q3 | gstack install? | Cannot register skills into this session (sandbox skills dir is read-only, no `bun`, and I cannot type into a terminal on your Windows machine). Cloned the repo and am following the skill files manually. | 2026-07-26 |
| Q4 | Razorpay test keys? | None available — provider is mocked/stubbed. Payment findings are code-level plus whatever the UI reveals without live keys. | 2026-07-26 |

---

## Phase 5 additions (2026-07-26)

Answered by you in Phase 5 Step 0:

| # | Question | Answer |
|---|---|---|
| Q13 | What to do about the uncommitted payment diff? | Review and report, do not commit. Done — see `04` §"Review of the uncommitted payment workstream" |
| Q14 | Session mode? | Verification only, no code written |
| Q15 | Razorpay test keys? | Still none. Payments remain code-review-only |
| Q16 | Customer or pipeline in any vertical? | **None named.** The Apparel-first recommendation in `customization-plan.md` §C.2 stands |

New, needing your answer:

**Q17. Run the four diagnostic commands in `04` §P0-2 and paste the output.**
This is the single highest-value action available. I narrowed the 500 to "every
path that reads the `plans` table", with a leading hypothesis that the DB is
behind migration `0010` and lacks `razorpay_plan_id`. One traceback confirms or
kills it. **[BLOCKING for all payment work]**

**Q18. Should industry access be gated by plan?** (`04` NEW-1)
Every tenant's JWT carries all five industries (`database.py:283`), so the
deny-by-default check at `tenant_context.py:114-138` never denies. A tenant with
no subscription can use all five verticals. Not a security hole — a monetization
decision. It interacts directly with `customization-plan.md` §A.8's per-vertical
billing models, so it is worth deciding before that work starts.

**Q19. Do you agree with the three-commit split?** (`04`, same section)
(a) payment hardening + migration `0017` + tests + scripts, (b) the `file_import`
rework (+318, unreviewed by this audit), (c) everything else. The concern is that
committing `subscription_manager.py` without `0017` ships code reading
`Plan.trial_days` against a DB with no such column.

**Q20. Should `qa_artifacts/` be committed or gitignored?**
Untracked, contains `.xlsx`, `.json`, and scratch `.py`.

**Q21. Are the CRLF→LF warnings expected?**
`git diff` emits line-ending warnings across many files. Check `.gitattributes`
before committing so the real diff is not swamped.

---

## Resolved 2026-07-27 (money-path session)

| # | Question | Answer |
|---|---|---|
| Q5 | Commit the payment diff? | **Done — `d074e35`.** The reason it had never landed: a zero-byte `.git/index.lock` dated 2026-07-21 made every `git add` fail for six days. |
| Q8 | `tenants.tier` vs `subscriptions.plan_id` — which is authoritative? | **`subscriptions`.** `tenants.tier` is written and never read: every creation path hardcodes `growth`, no subscription transition updates it, and 10 of 11 tenants sit at that default including six with no subscription at all. Full reasoning in `05` and in `app/core/entitlement.py`'s module docstring. |
| Q17 | Run the four P0-2 diagnostics | **Done, and they killed the hypothesis.** DB was at `0016`, not behind `0010`, and `razorpay_plan_id` was present. Real cause: `0017` unapplied while the ORM mapped `plans.trial_days`. |
| Q19 | Agree the three-commit split? | **Superseded.** Landed as six commits, one per item. The two-file commit in the brief was not viable — it would not have imported. |
| Q21 | Are the CRLF→LF warnings expected? | **Yes, benign.** `.gitattributes` already sets `* text=auto eol=lf`. |
| — | Gate scope: `/billing/usage` and onboarding uploads | You delegated. **Left ungated**, reasoning in `05`. |

---

## New, needing your answer

**Q22. Which auth mode do you actually ship — Firebase or dev-fallback?**
The industry token re-mint (`524fd29`) only works in dev-fallback. In Firebase
mode `ind` is a custom claim set at provisioning, so the equivalent fix is
`set_custom_user_claims` plus a client-side `getIdToken(true)`. I could not
implement or verify it because no Firebase project is configured.
**This is what keeps `03` liability 3 open, and with it the "do not sell into
pharma" guidance.**

**Q23. `tenants.tier` and `tenants.status` — drop, or maintain?**
Nothing reads them and nothing updates them. Either delete the columns, or have
`SubscriptionManager` maintain them as a denormalised read-model on every status
transition. Leaving them as dead-but-plausible state is the worst option: the
next person to write a feature will read `tenants.tier` and ship the same bug
this session just fixed.

**Q24. API usage metering has never recorded anything.**
`usage_metering.py:25` includes `"/"` in `_FREE_PATHS`, and `:52` does
`any(path.startswith(p) …)` — true for every path. `api_request` metering is
dead code, so overage on that meter can never bill. Is `api_request` overage
something you intend to charge for?

**Q25. Two duplicate stacks are running on your machine.**
A bare-metal uvicorn was shadowing Docker on port 8000 (now stopped), and the ML
API is still running bare-metal on 8001 alongside the Docker `ml-api`. Also
`backend/.venv` is Python 3.14.3 while `pyproject.toml` requires `>=3.12` and
the image pins 3.12. Which stack is canonical for your day-to-day work? Running
dev on a different minor than CI and production is how environment-specific bugs
get missed — and in this case it cost two audit rounds.

---

## Open — blocking

**Q5. ~~RESOLVED, and the answer is worse than expected.~~ CLOSED 2026-07-27 — see above.**
The running backend is stale, and the reason is that **the payment fixes were
never committed**. `HEAD` is `65023e1` and still contains
`trial_days: int | None = Field(default=14, ge=0, le=60)`. There are 462
uncommitted lines across `backend/app/routers/billing.py` and
`backend/app/services/billing/subscription_manager.py`.

Because `build-images.yml` builds from the committed tree, these fixes cannot
reach staging or production. **What I need:** review and commit that diff, deploy,
then tell me and I will re-run the P0 list. Note there are also uncommitted
changes in ~20 other files (models, connectors, frontend) that I have not
reviewed — someone should check whether those are intentional before committing
wholesale.

**Q6. Razorpay keys are blank. STILL BLOCKING, and now it is the only thing
between you and taking real money.**
Everything else on the purchase path works. `POST /billing/subscription`
currently returns 503 *because* the misconfiguration guard is doing its job. Set
`rzp_test_*` keys, run `python -m scripts.sync_razorpay_plans` (fixed this
session — it previously crashed on an import), and the checkout can be exercised
end to end for the first time.
With `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` unset, `/billing/config` returns
`configured: false`, the checkout modal never opens, and priced plans hit the
`BillingNotConfiguredError` guard (`subscription_manager.py:133-144`). I can
test the *gate* and the *state machine* but not a real checkout.
**What I need:** either `rzp_test_*` keys, or your confirmation that I should
report the payment section as "untestable live, code-review only".

---

## Open — non-blocking

**Q7. Is GST / Indian tax handling in scope?**
Prices are ₹-denominated (`SubscriptionGate.tsx:402`) but there is no tax logic
anywhere. For an Indian SaaS selling B2B, GST invoicing with a GSTIN field is
usually a legal requirement, not a nice-to-have. Flagging as an assumption for
now.

**Q8. ~~What is the intended relationship between `tenants.tier` and
`subscriptions.plan_id`?~~ ANSWERED 2026-07-27 — `subscriptions`. See above and
Q23 for the reconciliation that is still owed.**

**Q9. Is the connector catalogue aspirational?**
`app/connectors/catalog.py` advertises Kafka, AWS, Snowflake, Postgres, MySQL
and more, but `app/services/integrations/` implements only Shopify, WooCommerce,
generic SQL, and file import. Are the rest roadmap, or did I miss the handlers?

**Q10. Billing plan pricing — who owns the number?**
Prices are hardcoded in `SubscriptionGate.tsx:402,447`, stored in
`plans.base_price_cents`, and configured again in the Razorpay dashboard. Three
sources of truth. Which is canonical?

**Q11. Vertical priority for Phase 4.**
Phase 4C asks me to recommend which vertical to template first. I will make a
recommendation from the code and market logic, but if you already have paying
customers or a strong pipeline in one of the five, that should override my
analysis. Do you?

**Q12. `backend/test_venv/` is committed to the repo.**
A checked-in virtualenv. Almost certainly accidental. Want it removed? (I am not
modifying anything this run — flagging only.)
