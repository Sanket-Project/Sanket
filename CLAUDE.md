# CLAUDE.md — SANKET / Prisma

Claude Code specifics for this repository.

> **Read [AGENTS.md](AGENTS.md) first. It is authoritative.**
>
> AGENTS.md carries the operating rules that bind *every* agent in this repo —
> the Iron Law of workflow invocation, the Superpowers workflows for planning,
> TDD, systematic debugging and verification, and the project rules on RLS,
> payment keys, icons, and honest failure. Where this file and AGENTS.md
> disagree, AGENTS.md wins.
>
> This file adds only what is Claude Code specific: the gstack skill pack and
> the browser rule.

## Project

SANKET is an industry-scoped predictive analytics & supply-chain SaaS.
FastAPI backend + React/Vite SPA + a separate ML inference API, on PostgreSQL 16
with row-level security. See `README.md` and `docs/ARCHITECTURE.md`.

**Each workspace is scoped to exactly one industry**, chosen when it is created
and inherited by every member; it locks once setup completes or data arrives.
That is a *product* boundary, enforced by `app/core/industry_scope.py`. Tenant
isolation is the separate *security* boundary, enforced by PostgreSQL RLS — both
still apply, and they answer different questions. See
`docs/superpowers/specs/2026-08-31-industry-scoped-workspace-design.md`.

Supported verticals (a customer picks one): Apparel & Fashion, Consumer
Electronics, Pharmaceuticals, Agriculture (Agro), and Hardware.

---

## gstack

This project uses [gstack](https://github.com/garrytan/gstack) — Garry Tan's
open-source Claude Code skill pack. It turns Claude Code into a virtual
engineering team: a CEO, an eng manager, a designer, a reviewer, a QA lead, a
security officer, and a release engineer, each as a slash command.

### Install

```bash
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
  && cd ~/.claude/skills/gstack && ./setup
```

**Not currently installed on this machine.** If `~/.claude/skills/gstack`
is absent, the skills below are unavailable — say so and fall back to the
manual workflow in AGENTS.md §3 rather than claiming to have used them.

Requires [Bun](https://bun.sh/) v1.0+, Git, and Node.js (on Windows).
`./setup` builds the `browse` binary and registers every skill with Claude Code.
Re-run `./setup` after any `git pull`. Use `/gstack-upgrade` to update.

### Browser rule — READ THIS

**Use the `/browse` skill for ALL web browsing. Never call the
`mcp__claude-in-chrome__*` tools directly.**

`/browse` is a compiled headless-Chromium daemon with ~70+ commands, ref-based
element selection (`$B snapshot -i` → `$B click @e30`), and roughly 100–200ms per
call with zero context-token overhead. Driving Chrome through the MCP tools
instead burns context on every screenshot and is an order of magnitude slower.

```bash
B=~/.claude/skills/gstack/browse/dist/browse
$B goto http://localhost:5173
$B snapshot -i          # interactive refs
$B click @e12
$B text                 # clean page text
$B screenshot /tmp/x.png
```

Full reference: `~/.claude/skills/gstack/BROWSER.md`.

**Known exception:** `/browse` runs wherever the agent's shell runs. If the agent
shell is sandboxed away from the machine hosting the app (e.g. Cowork's isolated
Linux workspace vs. a dev server on the developer's `localhost`), `/browse`
cannot reach the target and Claude-in-Chrome is the only path. Say so explicitly
when falling back rather than doing it silently.

### Precedence: Superpowers owns the core loop

Superpowers (see [AGENTS.md](AGENTS.md)) owns plan → build → debug → verify.
gstack keeps what Superpowers does not cover. Do not run both for one purpose:
use `superpowers:systematic-debugging` over `/investigate`,
`superpowers:brainstorming` + `writing-plans` over `/autoplan`, and
`superpowers:requesting-code-review` over `/review`. `/browse`, `/cso` and
`/ship` have no Superpowers equivalent and remain the right tool.

### Skills to lean on in this repo

| Skill | Use for |
|---|---|
| `/investigate` | Root-cause debugging. Iron Law: no fixes without a root cause. |
| `/browse` | All web browsing and UI driving. |
| `/qa` | Systematic QA of the running app, then fix + re-verify each bug atomically. |
| `/qa-only` | Same sweep, report-only, no code changes. |
| `/office-hours` | Pressure-test a product idea before building it. |
| `/autoplan` | Run the CEO + design + eng + DX plan reviews back-to-back. |
| `/plan-ceo-review` | Scope and ambition review of a plan. |
| `/cso` | OWASP + STRIDE security audit — relevant given RLS + GxP scope. |
| `/review` | Pre-landing PR review. |
| `/ship` | Test, bump VERSION, changelog, commit, push, open PR. |

### Full skill list

**Planning & strategy** — `/office-hours`, `/spec`, `/autoplan`,
`/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`,
`/plan-devex-review`, `/plan-tune`

**Build & debug** — `/investigate`, `/health`, `/careful`, `/guard`, `/freeze`,
`/unfreeze`, `/codex`, `/pair-agent`, `/learn`

**Design** — `/design-consultation`, `/design-html`, `/design-review`,
`/design-shotgun`

**QA & security** — `/qa`, `/qa-only`, `/cso`, `/review`, `/devex-review`,
`/benchmark`, `/benchmark-models`

**Browser** — `/browse`, `/scrape`, `/skillify`, `/connect-chrome`,
`/open-gstack-browser`, `/setup-browser-cookies`

**Ship & operate** — `/ship`, `/land-and-deploy`, `/setup-deploy`, `/canary`,
`/landing-report`, `/retro`

**Docs** — `/document-generate`, `/document-release`, `/diagram`, `/make-pdf`

**iOS** (not used here) — `/ios-qa`, `/ios-fix`, `/ios-clean`, `/ios-sync`,
`/ios-design-review`

**Context & meta** — `/context-save`, `/context-restore`, `/gstack-upgrade`,
`/setup-gbrain`, `/sync-gbrain`

---

## Repo conventions

- Backend: Python 3.11+, FastAPI, SQLAlchemy, Alembic. Managed with `uv`.
- Frontend: Vite + React + TypeScript + Tailwind. Playwright for E2E, Vitest for unit.
- Tenant isolation is enforced by PostgreSQL RLS. Never bypass it with a
  superuser connection in application code.
- Payments run through Razorpay. Never commit live keys; test with `rzp_test_*`.
- Audit docs live in `docs/audit/`, strategy docs in `docs/strategy/`.
