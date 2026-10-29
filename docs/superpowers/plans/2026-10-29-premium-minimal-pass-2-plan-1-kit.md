# Premium Minimal Pass 2 — Plan 1: harness, navigation, foundation and component kit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the review harness, restore Hybrid Forecasts to the navigation,
remove three unrouted pages, and build the shared component kit that Plan 2
(screen migration) will consume.

**Architecture:** Additive components in `frontend/src/components/ui/` and
`frontend/src/components/charts/kit/`, each backward compatible and unit-tested
before it exists. Only Task 2 and Task 3 change user-visible routes or
navigation. No page is migrated onto the kit in this plan; that is Plan 2.

**Tech Stack:** React 18, TypeScript 5.6, Vite 5, Tailwind 3.4, Recharts 2.13,
TanStack Query 5, Zustand 5, Vitest 2 + Testing Library, react-router-dom 6.

**Spec:** `docs/superpowers/specs/2026-10-29-premium-minimal-pass-2-design.md`

**Plan 2** (screen migration, groups 1–7) is written after this plan lands,
against the real kit APIs and the then-current page code.

## Global Constraints

- No backend, API-contract, schema, auth, tenancy or industry-scope changes. `src/api/*` is consumed as is, except for deleting the three unused clients in Task 2.
- No new runtime dependency.
- Icons import only from `@/components/ui/icons`.
- Missing data renders as unavailable ("—" plus a reason), never as 0. Observed zeros render as 0.
- Palette unchanged: tokens in `src/styles/index.css` only; no raw hex in components.
- Motion: 140ms feedback, 200ms disclosures; the existing global `prefers-reduced-motion` rule in `index.css` already zeroes transitions and animations.
- Existing component APIs stay backward compatible (`Table`, `KPICard`, `Skeleton`, `EmptyState`, `Modal`).
- Every commit ends with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- Run commands from `frontend/`. Single test: `npx vitest run <path>`. Full suite: `npx vitest run` (~130s). Typecheck: `npx tsc --noEmit`.
- Baseline: `tsc` clean; Vitest 82 files / 387 tests passing (checkpoint `7e47945`).

---

### Task 1: Review harness renders every screen without a fixture

**Root cause (verified):** without `fixture=planning`, harness requests reach the
real backend and return 401. `src/api/client.ts:70-100` treats a 401 as an
expired session and calls `logout()`, which clears `industry`. `AppShell` then
calls `useWorkspaceIndustry()`, which throws, and the page is blank.

**Fix:** when no fixture is requested, install an adapter that answers every
request with a 503. Pages then render their own unavailable states, and no
logout fires.

**Files:**
- Create: `frontend/e2e/unavailable-fixture.ts`
- Modify: `frontend/e2e/design-harness.tsx:19-23`

**Interfaces:**
- Produces: `installUnavailableFixture(): void`

- [ ] **Step 1: Confirm the failure**

Open `http://localhost:5173/e2e/review.html?screen=SalesAnalytics` (preview
server `sanket-frontend`). Expected: a blank page, and the console shows
`useWorkspaceIndustry was called outside an authenticated workspace`.

- [ ] **Step 2: Create the fixture**

```ts
// frontend/e2e/unavailable-fixture.ts
// Synthetic browser-review responses only. Never imported by src/ or shipped.
// Every request fails as "service unavailable" so screens show their honest
// unavailable states. A 503 (not 401) keeps the client from logging out.
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { apiClient } from "../src/api/client";

export function installUnavailableFixture() {
  apiClient.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const response = {
      data: { detail: "Unavailable in isolated design review" },
      status: 503,
      statusText: "Service Unavailable",
      headers: {},
      config,
    } as AxiosResponse;
    throw new AxiosError("Unavailable in isolated design review", "ERR_BAD_RESPONSE", config, null, response);
  };
}
```

- [ ] **Step 3: Install it when no fixture is set**

In `frontend/e2e/design-harness.tsx`, replace:

```ts
if (fixture === "planning") {
  const { installPlanningFixture } = await import("./planning-fixture");
  installPlanningFixture();
}
```

with:

```ts
if (fixture === "planning") {
  const { installPlanningFixture } = await import("./planning-fixture");
  installPlanningFixture();
} else {
  const { installUnavailableFixture } = await import("./unavailable-fixture");
  installUnavailableFixture();
}
```

- [ ] **Step 4: Verify in the browser**

Reload `?screen=SalesAnalytics`, then `?screen=Inventory` and `?screen=Decisions`.
Expected for each: the shell and the page heading render, there is no
`useWorkspaceIndustry` error in the console, and no request returns 401.
`?screen=Dashboard&fixture=planning` still renders the populated dashboard.

- [ ] **Step 5: Commit**

```bash
git add e2e/unavailable-fixture.ts e2e/design-harness.tsx
git commit -m "fix(e2e): review harness answers 503 without a fixture so 401 logout cannot blank screens"
```

---

### Task 2: Remove WhatIfScenario, Signals and ForecastAccuracy

**Files:**
- Delete: `src/pages/WhatIfScenario.tsx`, `src/pages/WhatIfScenario.test.tsx`, `src/api/scenarios.ts`
- Delete: `src/pages/Signals.tsx`, `src/api/signals.ts`, `src/components/signals/EconomicIndicators.tsx`, `src/components/signals/SocialBuzz.tsx`
- Delete: `src/pages/ForecastAccuracy.tsx`, `src/pages/ForecastAccuracy.test.tsx`, `src/pages/forecastAccuracyRules.ts`, `src/api/forecastAccuracy.ts`
- Modify: `frontend/e2e/design-harness.tsx` (screen map)
- Keep: `src/components/ai/ScenarioAssistant.tsx` (covered by `components/ai/Interactive.test.tsx`), `src/components/signals/TrendPanel.tsx`, `src/components/charts/ScenarioBands.tsx` (both used by Hybrid Forecasts)

- [ ] **Step 1: Re-verify nothing else imports them**

Run from `frontend/src`:

```bash
grep -rln "pages/WhatIfScenario\|pages/Signals\|pages/ForecastAccuracy\|forecastAccuracyRules\|api/scenarios\"\|api/signals\"\|api/forecastAccuracy\"\|signals/EconomicIndicators\|signals/SocialBuzz" --include=*.ts --include=*.tsx . ../e2e
```

Expected: only files in the delete list, plus `../e2e/design-harness.tsx`, which
references them by page name in its `screens` map. If anything else appears,
stop and report.

- [ ] **Step 2: Delete the files**

```bash
git rm src/pages/WhatIfScenario.tsx src/pages/WhatIfScenario.test.tsx src/api/scenarios.ts \
  src/pages/Signals.tsx src/api/signals.ts src/components/signals/EconomicIndicators.tsx src/components/signals/SocialBuzz.tsx \
  src/pages/ForecastAccuracy.tsx src/pages/ForecastAccuracy.test.tsx src/pages/forecastAccuracyRules.ts src/api/forecastAccuracy.ts
```

- [ ] **Step 3: Drop the harness entries**

In `frontend/e2e/design-harness.tsx`, replace:

```ts
  ForecastAccuracy: ["ForecastAccuracy", "ForecastAccuracyPage"], HybridForecasts: ["HybridForecasts", "HybridForecastsPage"],
  WhatIfScenario: ["WhatIfScenario", "WhatIfScenarioPage"], Signals: ["Signals", "SignalsPage"],
```

with:

```ts
  HybridForecasts: ["HybridForecasts", "HybridForecastsPage"],
```

- [ ] **Step 4: Verify**

Run: `npx tsc --noEmit` → no output.
Run: `npx vitest run` → all files pass. Expected count: 80 files, with the 2
deleted test files' tests gone.

- [ ] **Step 5: Commit**

```bash
git add -A src e2e/design-harness.tsx
git commit -m "chore(ui): remove unrouted WhatIfScenario, Signals and ForecastAccuracy pages"
```

---

### Task 3: Restore Hybrid Forecasts route and sidebar entry

**Files:**
- Modify: `src/App.tsx` (lazy import and the `forecasts/hybrid` route)
- Modify: `src/components/layout/Sidebar.tsx:98-102` (`NAV_PLAN`) and its icon import
- Modify: `src/pages/Forecasts.tsx:632` (link the "Hybrid forecasts" sentence)
- Test: `src/components/layout/Sidebar.test.tsx`, create `src/pages/HybridRoute.test.tsx`

**Interfaces:**
- Produces: route `/workspace/forecasts/hybrid` → `HybridForecastsPage`; nav label `"Hybrid Forecasts"`

- [ ] **Step 1: Write the failing Sidebar test**

Append to `src/components/layout/Sidebar.test.tsx`. It reuses the file's
existing mocks and `setViewport`:

```tsx
it("lists Hybrid Forecasts directly after Forecasts in the Plan group", () => {
  setViewport(true);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/workspace"]}><Sidebar /></MemoryRouter>
    </QueryClientProvider>,
  );
  const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
  const forecasts = hrefs.indexOf("/workspace/forecasts");
  expect(forecasts).toBeGreaterThan(-1);
  expect(hrefs[forecasts + 1]).toBe("/workspace/forecasts/hybrid");
  expect(screen.getByRole("link", { name: /Hybrid Forecasts/ })).toBeInTheDocument();
});
```

- [ ] **Step 2: Write the failing route test**

```tsx
// src/pages/HybridRoute.test.tsx
import { render, screen } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/components/layout/AppShell", () => ({ AppShell: () => <Outlet /> }));
vi.mock("@/hooks/useWebSocket", () => ({ useWebSocket: () => ({ subscribe: () => () => {} }) }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import App from "@/App";
import { useAuthStore } from "@/stores/auth";

beforeEach(() => {
  useAuthStore.setState({ isAuthenticated: true, ready: true, industry: "fashion", onboarding: null, bootstrap: vi.fn() });
});

it("renders Hybrid Forecasts at /workspace/forecasts/hybrid instead of redirecting", async () => {
  window.history.replaceState({}, "", "/workspace/forecasts/hybrid");
  render(<App />);
  expect(await screen.findByRole("button", { name: "Run scenario" })).toBeInTheDocument();
  expect(window.location.pathname).toBe("/workspace/forecasts/hybrid");
});
```

- [ ] **Step 3: Run both and watch them fail**

Run: `npx vitest run src/components/layout/Sidebar.test.tsx src/pages/HybridRoute.test.tsx`
Expected: the Sidebar test fails because `hrefs[forecasts + 1]` is
`/workspace/products`. The route test fails on the pathname, which becomes
`/workspace/forecasts`, or because "Run scenario" never appears.

- [ ] **Step 4: Implement**

In `src/App.tsx`, after the `ForecastsPage` lazy import, add:

```tsx
const HybridForecastsPage = lazy(() =>
  import("@/pages/HybridForecasts").then((m) => ({ default: m.HybridForecastsPage }))
);
```

Replace:

```tsx
            <Route path="forecasts/hybrid" element={<Navigate to="/workspace/forecasts" replace />} />
```

with:

```tsx
            <Route path="forecasts/hybrid" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><HybridForecastsPage /></Suspense></ErrorBoundary>} />
```

Keep the `Navigate` import, because other routes still use it (`grep -n "<Navigate" src/App.tsx`).

In `src/components/layout/Sidebar.tsx`, add `Layers` to the existing
`@/components/ui/icons` import, then change `NAV_PLAN` to:

```tsx
const NAV_PLAN: NavEntry[] = [
  { to: "/workspace", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/workspace/decisions", label: "Decisions", icon: Target },
  { to: "/workspace/forecasts", label: "Forecasts", icon: LineChart, exact: true },
  { to: "/workspace/forecasts/hybrid", label: "Hybrid Forecasts", icon: Layers },
];
```

`exact: true` on Forecasts stops both entries from showing as active on the
hybrid URL. Check that `NavItem` honours `exact` the same way it does for
Dashboard (`grep -n "exact" src/components/layout/Sidebar.tsx`).

In `src/pages/Forecasts.tsx:632`, replace the fallback string:

```tsx
"No external signals applied to this forecast — trend and signal adjustment happen only in Hybrid forecasts."
```

with:

```tsx
<>No external signals applied to this forecast — trend and signal adjustment happen only in <Link to="/workspace/forecasts/hybrid" className="font-medium text-accent underline-offset-2 hover:underline">Hybrid forecasts</Link>.</>
```

Add `Link` to the file's `react-router-dom` import if it is not already there.

- [ ] **Step 5: Run the tests and see them pass**

Run: `npx vitest run src/components/layout/Sidebar.test.tsx src/pages/HybridRoute.test.tsx src/pages/HybridForecasts.test.tsx src/pages/Forecasts.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/App.tsx src/components/layout/Sidebar.tsx src/components/layout/Sidebar.test.tsx src/pages/HybridRoute.test.tsx src/pages/Forecasts.tsx
git commit -m "feat(nav): restore Hybrid Forecasts route and sidebar entry"
```

---

### Task 4: Foundation — motion tokens, type scale, focus ring

**Files:**
- Modify: `src/styles/index.css` (`:root` vars; `@layer components`)
- Modify: `tailwind.config.ts` (`transitionDuration`, `transitionTimingFunction`)
- Test: create `src/styles/foundation-tokens.test.ts`

**Interfaces:**
- Produces: Tailwind `duration-fast`, `duration-base`, `ease-standard`. Classes `.t-page .t-section .t-card .t-kpi .t-label .t-body .t-table .focus-ring`.

- [ ] **Step 1: Write the failing test**

```ts
// src/styles/foundation-tokens.test.ts
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import config from "../../tailwind.config";

// Same cwd-relative path as text-contrast.test.ts (Vitest runs from frontend/).
const css = readFileSync("src/styles/index.css", "utf8");

it("defines motion tokens at the DESIGN.md durations", () => {
  expect(css).toMatch(/--dur-fast:\s*140ms/);
  expect(css).toMatch(/--dur:\s*200ms/);
  expect(css).toMatch(/--ease:\s*cubic-bezier\(0\.2,\s*0,\s*0,\s*1\)/);
});

it("exposes motion tokens as Tailwind utilities", async () => {
  const { css: out } = await postcss([tailwindcss({ ...config, content: [{ raw: "duration-fast duration-base ease-standard", extension: "html" }] })]).process("@tailwind utilities;", { from: undefined });
  expect(out).toContain(".duration-fast");
  expect(out).toContain(".duration-base");
  expect(out).toContain(".ease-standard");
});

it("defines the type scale and focus ring classes", () => {
  for (const cls of [".t-page", ".t-section", ".t-card", ".t-kpi", ".t-label", ".t-body", ".t-table", ".focus-ring"]) {
    expect(css).toContain(cls);
  }
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/styles/foundation-tokens.test.ts` → FAIL (`--dur-fast` missing).

- [ ] **Step 3: Implement**

In `src/styles/index.css`, inside the first `:root {` block (line 11), add:

```css
  --dur-fast: 140ms;
  --dur: 200ms;
  --ease: cubic-bezier(0.2, 0, 0, 1);
```

Inside `@layer components {`, after the `.surface` rule, add:

```css
  /* Type scale — DESIGN.md sizes. Prefer these over ad-hoc text-[Npx]. */
  .t-page    { @apply font-heading text-[28px] font-semibold leading-tight tracking-tight text-content; }
  .t-section { @apply font-heading text-lg font-semibold tracking-tight text-content; }
  .t-card    { @apply font-heading text-[15px] font-semibold tracking-tight text-content; }
  .t-kpi     { @apply font-heading text-[28px] font-semibold leading-none tracking-tight text-content tabular-nums; }
  .t-label   { @apply text-xs font-medium text-content-muted; }
  .t-body    { @apply text-sm leading-relaxed text-content-muted; }
  .t-table   { @apply text-[13px] tabular-nums; }

  /* One focus treatment for every kit control. */
  .focus-ring { @apply outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent; }
```

In `tailwind.config.ts`, inside `theme.extend`, add:

```ts
      transitionDuration: { fast: "var(--dur-fast)", base: "var(--dur)" },
      transitionTimingFunction: { standard: "var(--ease)" },
```

- [ ] **Step 4: Run and see it pass**

Run: `npx vitest run src/styles/` → all PASS, including the existing contrast and opacity tests.

- [ ] **Step 5: Commit**

```bash
git add src/styles/index.css src/styles/foundation-tokens.test.ts tailwind.config.ts
git commit -m "feat(design): motion tokens, type-scale utilities and shared focus ring"
```

---

### Task 5: State views and QueryBoundary

**Files:**
- Create: `src/components/ui/StateViews.tsx`
- Modify: `src/components/ui/Skeleton.tsx` (add `SkeletonChart`, `SkeletonTable`)
- Test: create `src/components/ui/StateViews.test.tsx`

**Interfaces:**
- Consumes: `EmptyState` (`components/ui/EmptyState.tsx`), `Button`, icons `AlertTriangle`, `CircleDashed`, `RefreshCw`
- Produces:
  - `LoadingState({ variant?: "lines" | "card" | "chart" | "table"; rows?: number; label?: string })`
  - `ErrorState({ title?: string; message?: ReactNode; onRetry?: () => void })`
  - `UnavailableState({ title: string; reason: ReactNode; action?: ReactNode })`
  - `QueryBoundary<T>({ query: { data: T | undefined; isLoading: boolean; isError: boolean; error?: unknown; refetch?: () => unknown }; loading?: ReactNode; isEmpty?: (data: T) => boolean; empty?: ReactNode; errorTitle?: string; children: (data: T) => ReactNode })`
  - `SkeletonChart({ height?: number })`, `SkeletonTable({ rows?: number; columns?: number })`

- [ ] **Step 1: Write the failing tests**

```tsx
// src/components/ui/StateViews.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ErrorState, LoadingState, QueryBoundary, UnavailableState } from "./StateViews";

it("announces loading politely", () => {
  render(<LoadingState label="Loading sales" />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading sales");
});

it("offers a retry that calls back", () => {
  const onRetry = vi.fn();
  render(<ErrorState message="Server said no" onRetry={onRetry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Server said no");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(onRetry).toHaveBeenCalledOnce();
});

it("states why data is unavailable", () => {
  render(<UnavailableState title="No branch breakdown" reason="Sales were imported without branch identifiers." />);
  expect(screen.getByText("No branch breakdown")).toBeInTheDocument();
  expect(screen.getByText(/without branch identifiers/)).toBeInTheDocument();
});

it("QueryBoundary renders loading, error, empty and data in turn", () => {
  const base = { data: undefined as number[] | undefined, isLoading: true, isError: false, refetch: vi.fn() };
  const view = (q: typeof base) => (
    <QueryBoundary query={q} isEmpty={(d) => d.length === 0} empty={<p>Nothing yet</p>}>
      {(d) => <p>{d.length} rows</p>}
    </QueryBoundary>
  );
  const { rerender } = render(view(base));
  expect(screen.getByRole("status")).toBeInTheDocument();
  rerender(view({ ...base, isLoading: false, isError: true }));
  expect(screen.getByRole("alert")).toBeInTheDocument();
  rerender(view({ ...base, isLoading: false, data: [] }));
  expect(screen.getByText("Nothing yet")).toBeInTheDocument();
  rerender(view({ ...base, isLoading: false, data: [0, 0] }));
  expect(screen.getByText("2 rows")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/StateViews.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Add skeleton variants**

Append to `src/components/ui/Skeleton.tsx`:

```tsx
export const SkeletonChart = ({ height = 280 }: { height?: number }) => (
  <div className="animate-pulse rounded-xl bg-surface-2" style={{ height }} />
);

export const SkeletonTable = ({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) => (
  <div className="animate-pulse space-y-2">
    {Array.from({ length: rows }).map((_, r) => (
      <div key={r} className="grid gap-3" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {Array.from({ length: columns }).map((__, c) => <div key={c} className="h-4 rounded bg-surface-2" />)}
      </div>
    ))}
  </div>
);
```

- [ ] **Step 4: Implement StateViews**

```tsx
// src/components/ui/StateViews.tsx
import type { ReactNode } from "react";
import { AlertTriangle, CircleDashed, RefreshCw } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";
import { Skeleton, SkeletonCard, SkeletonChart, SkeletonTable } from "@/components/ui/Skeleton";
import { getErrorMessage } from "@/utils/errors";

export const LoadingState = ({ variant = "lines", rows = 3, label = "Loading" }: {
  variant?: "lines" | "card" | "chart" | "table"; rows?: number; label?: string;
}) => (
  <div role="status" aria-live="polite" aria-busy="true">
    <span className="sr-only">{label}</span>
    {variant === "card" ? <SkeletonCard /> : variant === "chart" ? <SkeletonChart /> : variant === "table" ? <SkeletonTable rows={rows} /> : <Skeleton rows={rows} />}
  </div>
);

export const ErrorState = ({ title = "Couldn't load this", message, onRetry }: {
  title?: string; message?: ReactNode; onRetry?: () => void;
}) => (
  <div role="alert" className="flex flex-col items-center px-4 py-8 text-center">
    <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400"><AlertTriangle size={18} aria-hidden="true" /></div>
    <p className="t-card">{title}</p>
    {message && <p className="t-body mt-1 max-w-sm">{message}</p>}
    {onRetry && <Button variant="secondary" size="sm" className="mt-4" icon={<RefreshCw size={14} aria-hidden="true" />} onClick={onRetry}>Try again</Button>}
  </div>
);

export const UnavailableState = ({ title, reason, action }: { title: string; reason: ReactNode; action?: ReactNode }) => (
  <div className="flex flex-col items-center px-4 py-8 text-center">
    <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-surface-3 text-content-subtle"><CircleDashed size={18} aria-hidden="true" /></div>
    <p className="t-card">{title}</p>
    <p className="t-body mt-1 max-w-sm">{reason}</p>
    {action && <div className="mt-4">{action}</div>}
  </div>
);

interface QueryLike<T> { data: T | undefined; isLoading: boolean; isError: boolean; error?: unknown; refetch?: () => unknown }

export function QueryBoundary<T>({ query, loading, isEmpty, empty, errorTitle, children }: {
  query: QueryLike<T>; loading?: ReactNode; isEmpty?: (data: T) => boolean; empty?: ReactNode; errorTitle?: string; children: (data: T) => ReactNode;
}) {
  if (query.isLoading) return <>{loading ?? <LoadingState />}</>;
  if (query.isError || query.data === undefined) {
    return <ErrorState title={errorTitle} message={query.error ? getErrorMessage(query.error, "The server did not respond.") : undefined} onRetry={query.refetch ? () => void query.refetch?.() : undefined} />;
  }
  if (isEmpty?.(query.data)) return <>{empty ?? null}</>;
  return <>{children(query.data)}</>;
}
```

`getErrorMessage(err: unknown, fallback?: string): string` is defined in `src/utils/errors.ts:11`.

- [ ] **Step 5: Run and see it pass**

Run: `npx vitest run src/components/ui/StateViews.test.tsx src/components/ui/Skeleton.test.tsx` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/ui/StateViews.tsx src/components/ui/StateViews.test.tsx src/components/ui/Skeleton.tsx
git commit -m "feat(ui): loading, error and unavailable state views with QueryBoundary"
```

---

### Task 6: Section

**Files:**
- Create: `src/components/ui/Section.tsx`
- Test: create `src/components/ui/Section.test.tsx`

**Interfaces:**
- Produces: `Section({ title: ReactNode; description?: ReactNode; actions?: ReactNode; divider?: boolean = true; id?: string; className?: string; children: ReactNode })`. Renders `<section aria-labelledby>` with an `h2`.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/Section.test.tsx
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Section } from "./Section";

it("is a labelled region with a level-2 heading and its actions", () => {
  render(<Section title="Stock movement" description="Last 30 days" actions={<button>Export</button>}><p>body</p></Section>);
  const region = screen.getByRole("region", { name: "Stock movement" });
  expect(region).toContainElement(screen.getByRole("heading", { level: 2, name: "Stock movement" }));
  expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
  expect(screen.getByText("Last 30 days")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/Section.test.tsx` → FAIL.

- [ ] **Step 3: Implement**

```tsx
// src/components/ui/Section.tsx
import clsx from "clsx";
import { useId, type ReactNode } from "react";

/** Groups content by heading and hairline instead of another card. */
export const Section = ({ title, description, actions, divider = true, id, className, children }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; divider?: boolean; id?: string; className?: string; children: ReactNode;
}) => {
  const headingId = useId();
  return (
    <section id={id} aria-labelledby={headingId} className={clsx("min-w-0", divider && "border-t border-line pt-6", className)}>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <h2 id={headingId} className="t-section">{title}</h2>
          {description && <p className="t-body mt-1">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
};
```

- [ ] **Step 4: Run and see it pass**

Run: `npx vitest run src/components/ui/Section.test.tsx` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/Section.tsx src/components/ui/Section.test.tsx
git commit -m "feat(ui): Section groups content without a card"
```

---

### Task 7: MetricTile and KPICard adapter

**Files:**
- Create: `src/components/ui/MetricTile.tsx`
- Modify: `src/components/charts/KPICard.tsx` (becomes an adapter; drops the unused `delta` and `sparkPoints`)
- Test: create `src/components/ui/MetricTile.test.tsx`

**Interfaces:**
- Produces:
  - `type Provenance = "recorded" | "estimated" | "forecast" | "heuristic"`
  - `MetricTile({ label: string; value: ReactNode | null | undefined; unit?: string; provenance: Provenance; hint?: ReactNode; tone?: "default" | "success" | "warning" | "danger"; icon?: ReactNode; href?: string; onClick?: () => void; unavailableReason?: string; className?: string })`
- `KPICard` keeps `label, value, icon, tone, subtitle` and maps them to `MetricTile` with `provenance="recorded"` and `hint={subtitle}`. No caller passes `delta` or `sparkPoints` (verified by grep), so both are removed.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/components/ui/MetricTile.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { MetricTile } from "./MetricTile";

it("labels where the number comes from", () => {
  render(<MetricTile label="Items sold" value="1,240" provenance="recorded" />);
  expect(screen.getByText("Recorded")).toBeInTheDocument();
  expect(screen.getByText("1,240")).toBeInTheDocument();
});

it("keeps an observed zero as 0", () => {
  render(<MetricTile label="Stockouts" value={0} provenance="recorded" />);
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.queryByText("—")).not.toBeInTheDocument();
});

it("shows a dash and the reason when the value is missing, never 0", () => {
  render(<MetricTile label="Revenue at risk" value={null} provenance="estimated" unavailableReason="No prices imported" />);
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("No prices imported")).toBeInTheDocument();
  expect(screen.queryByText("0")).not.toBeInTheDocument();
});

it("falls back to a generic reason when none is given", () => {
  render(<MetricTile label="Coverage" value={undefined} provenance="heuristic" />);
  expect(screen.getByText("Not available from current data")).toBeInTheDocument();
});

it("becomes a link when given href", () => {
  render(<MemoryRouter><MetricTile label="Open decisions" value={3} provenance="recorded" href="/workspace/decisions" /></MemoryRouter>);
  expect(screen.getByRole("link", { name: /Open decisions/ })).toHaveAttribute("href", "/workspace/decisions");
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/MetricTile.test.tsx` → FAIL.

- [ ] **Step 3: Implement MetricTile**

```tsx
// src/components/ui/MetricTile.tsx
import clsx from "clsx";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "@/components/ui/icons";

export type Provenance = "recorded" | "estimated" | "forecast" | "heuristic";

const PROVENANCE_LABEL: Record<Provenance, string> = {
  recorded: "Recorded", estimated: "Estimated", forecast: "Forecast", heuristic: "Heuristic",
};
// Recorded is solid; derived values are outlined so the difference survives greyscale.
const PROVENANCE_CLS: Record<Provenance, string> = {
  recorded: "bg-surface-3 text-content-muted",
  estimated: "border border-dashed border-line-strong text-content-muted",
  forecast: "border border-dashed border-accent/40 text-accent",
  heuristic: "border border-dashed border-amber-500/50 text-amber-700 dark:text-amber-300",
};
const TONE_ICON = {
  default: "bg-accent-soft text-accent",
  success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  warning: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  danger: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
};

interface Props {
  label: string;
  value: ReactNode | null | undefined;
  unit?: string;
  provenance: Provenance;
  hint?: ReactNode;
  tone?: keyof typeof TONE_ICON;
  icon?: ReactNode;
  href?: string;
  onClick?: () => void;
  unavailableReason?: string;
  className?: string;
}

export const MetricTile = ({ label, value, unit, provenance, hint, tone = "default", icon, href, onClick, unavailableReason, className }: Props) => {
  const missing = value === null || value === undefined;
  const interactive = Boolean(href || onClick);
  const body = (
    <>
      <div className="flex items-start gap-3">
        {icon && <div className={clsx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", TONE_ICON[tone])}>{icon}</div>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="t-label">{label}</span>
            <span className={clsx("rounded px-1.5 py-px text-[10px] font-medium", PROVENANCE_CLS[provenance])}>{PROVENANCE_LABEL[provenance]}</span>
          </div>
          <p className="mt-1.5 flex items-baseline gap-1.5">
            <span className="t-kpi">{missing ? "—" : value}</span>
            {!missing && unit && <span className="t-label">{unit}</span>}
          </p>
          {missing
            ? <p className="mt-1 text-xs text-content-subtle">{unavailableReason ?? "Not available from current data"}</p>
            : hint && <p className="mt-1 text-xs text-content-subtle">{hint}</p>}
        </div>
        {interactive && <ChevronRight size={16} aria-hidden="true" className="mt-1 shrink-0 text-content-subtle transition-transform duration-fast ease-standard group-hover:translate-x-0.5" />}
      </div>
    </>
  );
  const cls = clsx("group block min-w-0 rounded-2xl border border-line bg-surface p-4 text-left shadow-sm", interactive && "focus-ring transition-colors duration-fast ease-standard hover:border-line-strong", className);
  if (href) return <Link to={href} className={cls}>{body}</Link>;
  if (onClick) return <button type="button" onClick={onClick} className={clsx(cls, "w-full")}>{body}</button>;
  return <div className={cls}>{body}</div>;
};
```

- [ ] **Step 4: Replace KPICard with the adapter**

Replace the whole of `src/components/charts/KPICard.tsx` with:

```tsx
import { memo, type ReactNode } from "react";
import { MetricTile } from "@/components/ui/MetricTile";

interface Props {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
  subtitle?: string;
}

/** Legacy entry point: recorded values only. New code uses MetricTile with explicit provenance. */
export const KPICard = memo(function KPICard({ label, value, icon, tone = "default", subtitle }: Props) {
  return <MetricTile label={label} value={value} icon={icon} tone={tone} hint={subtitle} provenance="recorded" />;
});
```

- [ ] **Step 5: Verify, including KPICard callers**

Run: `npx tsc --noEmit` → no output. A type error here means some caller passes
`delta` or `sparkPoints`. Stop and report it.
Run: `npx vitest run src/components/ui/MetricTile.test.tsx src/pages/Decisions.test.tsx src/pages/FinancialImpact.test.tsx src/pages/industries` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/ui/MetricTile.tsx src/components/ui/MetricTile.test.tsx src/components/charts/KPICard.tsx
git commit -m "feat(ui): MetricTile with required provenance; KPICard becomes an adapter"
```

---

### Task 8: DataTable — sorting, loading, density, scroll region, mobile cards, selection

**Files:**
- Create: `src/hooks/useMediaQuery.ts`
- Modify: `src/components/ui/Table.tsx` (extends `Column<T>` and `Props<T>`; exports `DataTable` as an alias of `Table`)
- Test: create `src/components/ui/Table.test.tsx`

**Interfaces:**
- Produces:
  - `useMediaQuery(query: string): boolean`. Returns `false` when `window.matchMedia` is missing (jsdom), which keeps the desktop table.
  - `Column<T>` gains `sortValue?: (row: T) => string | number | null | undefined` and `priority?: "primary" | "secondary" | "hidden-mobile"`
  - `Props<T>` gains `loading?: boolean`, `loadingRows?: number` (default 5), `density?: "comfortable" | "compact"`, `maxHeight?: number | string`, `mobile?: "scroll" | "cards"` (default `"scroll"`), `selection?: { selected: Set<string>; onChange: (next: Set<string>) => void; label?: (row: T) => string }`, `caption?: string`
  - `export const DataTable = Table`

- [ ] **Step 1: Write the failing tests**

```tsx
// src/components/ui/Table.test.tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Table, type Column } from "./Table";

type Row = { id: string; name: string; qty: number | null };
const rows: Row[] = [{ id: "a", name: "Tee", qty: 5 }, { id: "b", name: "Dress", qty: null }, { id: "c", name: "Jacket", qty: 12 }];
const cols: Column<Row>[] = [
  { key: "name", header: "Product", render: (r) => r.name, sortValue: (r) => r.name, priority: "primary" },
  { key: "qty", header: "Qty", render: (r) => r.qty ?? "—", sortValue: (r) => r.qty, align: "right" },
];
const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);

afterEach(() => { // @ts-expect-error reset jsdom
  delete window.matchMedia; });

it("sorts by a column, toggles direction, keeps nulls last, and sets aria-sort", () => {
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} />);
  const qty = screen.getByRole("button", { name: "Qty" });
  fireEvent.click(qty);
  expect(names()).toEqual(["Tee", "Jacket", "Dress"]);
  expect(screen.getByRole("columnheader", { name: /Qty/ })).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(qty);
  expect(names()).toEqual(["Jacket", "Tee", "Dress"]);
  expect(screen.getByRole("columnheader", { name: /Qty/ })).toHaveAttribute("aria-sort", "descending");
});

it("leaves non-sortable headers as plain text", () => {
  render(<Table data={rows} columns={[{ key: "n", header: "Name", render: (r) => r.name }]} rowKey={(r) => r.id} />);
  expect(screen.queryByRole("button", { name: "Name" })).not.toBeInTheDocument();
});

it("renders skeleton rows while loading instead of the empty message", () => {
  render(<Table data={[]} columns={cols} rowKey={(r) => r.id} loading loadingRows={3} empty="Nothing" />);
  expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
  expect(screen.getAllByRole("row")).toHaveLength(4);
  expect(screen.queryByText("Nothing")).not.toBeInTheDocument();
});

it("exposes a caption for screen readers", () => {
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} caption="Top products" />);
  expect(screen.getByRole("table", { name: "Top products" })).toBeInTheDocument();
});

it("selects rows and all rows through labelled checkboxes", () => {
  const onChange = vi.fn();
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} selection={{ selected: new Set(["a"]), onChange, label: (r) => r.name }} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Dress" }));
  expect([...onChange.mock.calls[0][0]].sort()).toEqual(["a", "b"]);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select all rows" }));
  expect([...onChange.mock.calls[1][0]].sort()).toEqual(["a", "b", "c"]);
});

it("renders rows as cards on small screens when mobile='cards'", () => {
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({ matches: q.includes("max-width"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn() })) as unknown as typeof window.matchMedia;
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} mobile="cards" caption="Top products" />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  const list = screen.getByRole("list", { name: "Top products" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(3);
  expect(within(list).getByText("Jacket")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/Table.test.tsx` → FAIL (no sort buttons, no `aria-busy`, no caption, no list).

- [ ] **Step 3: Add useMediaQuery**

```ts
// src/hooks/useMediaQuery.ts
import { useEffect, useState } from "react";

const query$ = (q: string) => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(q) : null);

/** False when matchMedia is unavailable (tests, SSR), so callers default to the desktop layout. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => query$(query)?.matches ?? false);
  useEffect(() => {
    const mql = query$(query);
    if (!mql) return;
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, [query]);
  return matches;
}
```

- [ ] **Step 4: Implement the Table upgrade**

Replace `src/components/ui/Table.tsx` with:

```tsx
import clsx from "clsx";
import { useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp } from "@/components/ui/icons";
import { useMediaQuery } from "@/hooks/useMediaQuery";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
  /** Opt in to client-side sorting. Nulls sort last in both directions. */
  sortValue?: (row: T) => string | number | null | undefined;
  /** Mobile card placement when mobile="cards". */
  priority?: "primary" | "secondary" | "hidden-mobile";
}

interface Selection<T> {
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  label?: (row: T) => string;
}

interface Props<T> {
  data: T[];
  columns: Column<T>[];
  empty?: ReactNode;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  className?: string;
  loading?: boolean;
  loadingRows?: number;
  density?: "comfortable" | "compact";
  maxHeight?: number | string;
  mobile?: "scroll" | "cards";
  selection?: Selection<T>;
  caption?: string;
}

type Sort = { key: string; dir: "asc" | "desc" } | null;

const alignCls = (a?: "left" | "right" | "center") => (a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left");
const isInteractiveTarget = (t: EventTarget) => Boolean((t as HTMLElement).closest("button, a, input, select, textarea, [role='button']"));

function sortRows<T>(data: T[], columns: Column<T>[], sort: Sort): T[] {
  const col = sort && columns.find((c) => c.key === sort.key);
  if (!sort || !col?.sortValue) return data;
  const get = col.sortValue;
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...data].sort((a, b) => {
    const va = get(a), vb = get(b);
    const na = va === null || va === undefined, nb = vb === null || vb === undefined;
    if (na || nb) return na === nb ? 0 : na ? 1 : -1;
    return (typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), undefined, { numeric: true })) * sign;
  });
}

export function Table<T>({ data, columns, empty, rowKey, onRowClick, className, loading, loadingRows = 5, density = "comfortable", maxHeight, mobile = "scroll", selection, caption }: Props<T>) {
  const [sort, setSort] = useState<Sort>(null);
  const rows = useMemo(() => sortRows(data, columns, sort), [data, columns, sort]);
  const small = useMediaQuery("(max-width: 767px)");
  const cellPad = density === "compact" ? "px-3 py-2" : "px-4 py-3";

  if (!loading && data.length === 0) {
    return <div className="rounded-2xl border border-dashed border-line bg-surface-2 py-12 text-center text-sm font-medium text-content-subtle">{empty ?? "No results."}</div>;
  }

  const toggleRow = (key: string) => {
    if (!selection) return;
    const next = new Set(selection.selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    selection.onChange(next);
  };
  const allSelected = selection ? rows.length > 0 && rows.every((r) => selection.selected.has(rowKey(r))) : false;
  const toggleAll = () => selection?.onChange(allSelected ? new Set() : new Set(rows.map(rowKey)));
  const activate = (row: T) => onRowClick?.(row);

  if (small && mobile === "cards" && !loading) {
    const primary = columns.filter((c) => c.priority === "primary");
    const rest = columns.filter((c) => c.priority !== "primary" && c.priority !== "hidden-mobile");
    return (
      <ul aria-label={caption} className={clsx("min-w-0 space-y-2", className)}>
        {rows.map((row) => (
          <li key={rowKey(row)}
            tabIndex={onRowClick ? 0 : undefined}
            onClick={(e) => { if (!isInteractiveTarget(e.target)) activate(row); }}
            onKeyDown={(e) => { if (e.target === e.currentTarget && onRowClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(row); } }}
            className={clsx("focus-ring rounded-xl border border-line bg-surface p-3", onRowClick && "cursor-pointer")}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 font-medium text-content">{primary.map((c) => <div key={c.key}>{c.render(row)}</div>)}</div>
              {selection && <input type="checkbox" aria-label={`Select ${selection.label?.(row) ?? rowKey(row)}`} checked={selection.selected.has(rowKey(row))} onChange={() => toggleRow(rowKey(row))} />}
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {rest.map((c) => (<div key={c.key} className="min-w-0"><dt className="text-content-subtle">{c.header}</dt><dd className="tabular-nums text-content-muted">{c.render(row)}</dd></div>))}
            </dl>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className={clsx("min-w-0 overflow-auto rounded-2xl border border-line bg-surface", className)} style={maxHeight !== undefined ? { maxHeight } : undefined}>
      <table className="t-table w-full border-collapse" aria-busy={loading || undefined}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-10">
          <tr className="bg-surface-2">
            {selection && (
              <th scope="col" className={clsx(cellPad, "w-10 border-b border-line")}>
                <input type="checkbox" aria-label="Select all rows" checked={allSelected} onChange={toggleAll} />
              </th>
            )}
            {columns.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th key={c.key} scope="col" style={c.width ? { width: c.width } : undefined}
                  aria-sort={c.sortValue ? (active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none") : undefined}
                  className={clsx(cellPad, "whitespace-nowrap border-b border-line text-xs font-medium text-content-muted", alignCls(c.align))}>
                  {c.sortValue ? (
                    <button type="button" className={clsx("focus-ring inline-flex items-center gap-1 rounded hover:text-content", c.align === "right" && "flex-row-reverse")}
                      onClick={() => setSort(active && sort!.dir === "asc" ? { key: c.key, dir: "desc" } : { key: c.key, dir: "asc" })}>
                      {c.header}
                      {active ? (sort!.dir === "asc" ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />) : null}
                    </button>
                  ) : c.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: loadingRows }).map((_, i) => (
                <tr key={`skeleton-${i}`} className="border-b border-line last:border-0">
                  {selection && <td className={cellPad} />}
                  {columns.map((c) => <td key={c.key} className={cellPad}><div className="h-3.5 animate-pulse rounded bg-surface-2" /></td>)}
                </tr>
              ))
            : rows.map((row, i) => {
                const key = rowKey(row);
                return (
                  <tr key={key}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={(e) => { if (!isInteractiveTarget(e.target)) activate(row); }}
                    onKeyDown={(e) => { if (e.target === e.currentTarget && onRowClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(row); } }}
                    className={clsx("border-b border-line transition-colors duration-fast ease-standard last:border-0", i % 2 === 1 && "bg-surface-2/50", onRowClick && "focus-ring cursor-pointer hover:bg-accent-soft", selection?.selected.has(key) && "bg-accent-soft")}>
                    {selection && (
                      <td className={cellPad}>
                        <input type="checkbox" aria-label={`Select ${selection.label?.(row) ?? key}`} checked={selection.selected.has(key)} onChange={() => toggleRow(key)} />
                      </td>
                    )}
                    {columns.map((c) => <td key={c.key} className={clsx(cellPad, "font-medium text-content-muted tabular-nums", alignCls(c.align))}>{c.render(row)}</td>)}
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}

export const DataTable = Table;
```

Note: the previous hover class was `hover:bg-[var(--accent-soft)]`. `bg-accent-soft`
is the same token through the Tailwind `accent.soft` color.

- [ ] **Step 5: Run the new tests and every existing Table consumer**

Run: `npx vitest run src/components/ui/Table.test.tsx`
→ PASS.
Run: `grep -rln "components/ui/Table" src --include=*.tsx`, then run the
matching `*.test.tsx` files → PASS.
Run: `npx tsc --noEmit` → no output.

- [ ] **Step 6: Commit**

```bash
git add src/hooks/useMediaQuery.ts src/components/ui/Table.tsx src/components/ui/Table.test.tsx
git commit -m "feat(ui): DataTable sorting, loading rows, density, scroll region, mobile cards and selection"
```

---

### Task 9: Select and SegmentedControl

**Files:**
- Create: `src/components/ui/Select.tsx`, `src/components/ui/SegmentedControl.tsx`
- Test: create `src/components/ui/Select.test.tsx`, `src/components/ui/SegmentedControl.test.tsx`

**Interfaces:**
- Produces:
  - `Select(props: SelectHTMLAttributes<HTMLSelectElement> & { label?: ReactNode; hint?: ReactNode; error?: ReactNode; options?: { value: string; label: string; disabled?: boolean }[]; size?: "sm" | "md" })`. Forwards its ref. When `label` is omitted the caller must pass `aria-label`.
  - `SegmentedControl<V extends string>({ label: string; value: V; onChange: (v: V) => void; options: { value: V; label: ReactNode }[]; size?: "sm" | "md" })`

- [ ] **Step 1: Write the failing tests**

```tsx
// src/components/ui/Select.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Select } from "./Select";

it("associates label, hint and error with a native select", () => {
  const onChange = vi.fn();
  render(<Select label="Granularity" hint="Buckets on the chart" error="Pick one" value="day" onChange={onChange} options={[{ value: "day", label: "Daily" }, { value: "week", label: "Weekly" }]} />);
  const select = screen.getByRole("combobox", { name: "Granularity" });
  expect(select).toHaveAccessibleDescription(/Buckets on the chart/);
  expect(select).toHaveAccessibleDescription(/Pick one/);
  expect(select).toHaveAttribute("aria-invalid", "true");
  fireEvent.change(select, { target: { value: "week" } });
  expect(onChange).toHaveBeenCalled();
});
```

```tsx
// src/components/ui/SegmentedControl.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import { SegmentedControl } from "./SegmentedControl";

const Harness = () => {
  const [v, setV] = useState<"day" | "week" | "month">("day");
  return <SegmentedControl label="Granularity" value={v} onChange={setV} options={[{ value: "day", label: "Daily" }, { value: "week", label: "Weekly" }, { value: "month", label: "Monthly" }]} />;
};

it("is a radio group with one tab stop and arrow-key movement", () => {
  render(<Harness />);
  expect(screen.getByRole("radiogroup", { name: "Granularity" })).toBeInTheDocument();
  const daily = screen.getByRole("radio", { name: "Daily" });
  expect(daily).toBeChecked();
  expect(daily).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("radio", { name: "Weekly" })).toHaveAttribute("tabindex", "-1");
  fireEvent.keyDown(daily, { key: "ArrowRight" });
  expect(screen.getByRole("radio", { name: "Weekly" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Weekly" })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("radio", { name: "Weekly" }), { key: "ArrowLeft" });
  fireEvent.keyDown(screen.getByRole("radio", { name: "Daily" }), { key: "ArrowLeft" });
  expect(screen.getByRole("radio", { name: "Monthly" })).toBeChecked();
});

it("selects on click", () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole("radio", { name: "Monthly" }));
  expect(screen.getByRole("radio", { name: "Monthly" })).toBeChecked();
});
```

- [ ] **Step 2: Run and see them fail**

Run: `npx vitest run src/components/ui/Select.test.tsx src/components/ui/SegmentedControl.test.tsx` → FAIL.

- [ ] **Step 3: Implement Select**

```tsx
// src/components/ui/Select.tsx
import clsx from "clsx";
import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "@/components/ui/icons";

interface Props extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  options?: { value: string; label: string; disabled?: boolean }[];
  size?: "sm" | "md";
}

/** Native select for real keyboard and screen-reader behaviour, styled to the kit. */
export const Select = forwardRef<HTMLSelectElement, Props>(function Select({ label, hint, error, options, size = "md", className, id, children, ...rest }, ref) {
  const auto = useId();
  const selectId = id ?? auto;
  const hintId = hint ? `${selectId}-hint` : undefined;
  const errorId = error ? `${selectId}-error` : undefined;
  return (
    <div className={clsx("min-w-0", className)}>
      {label && <label htmlFor={selectId} className="t-label mb-1.5 block">{label}</label>}
      <div className="relative">
        <select ref={ref} id={selectId} aria-invalid={error ? true : undefined}
          aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
          className={clsx("focus-ring w-full appearance-none rounded-lg border bg-surface pl-3 pr-9 text-sm text-content transition-colors duration-fast ease-standard hover:border-line-strong disabled:opacity-60",
            size === "sm" ? "h-8" : "h-10", error ? "border-rose-500" : "border-line")}
          {...rest}>
          {options ? options.map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>) : children}
        </select>
        <ChevronDown size={14} aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-content-subtle" />
      </div>
      {hint && <p id={hintId} className="mt-1 text-xs text-content-subtle">{hint}</p>}
      {error && <p id={errorId} className="mt-1 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
    </div>
  );
});
```

- [ ] **Step 4: Implement SegmentedControl**

```tsx
// src/components/ui/SegmentedControl.tsx
import clsx from "clsx";
import { useRef, type KeyboardEvent, type ReactNode } from "react";

interface Props<V extends string> {
  label: string;
  value: V;
  onChange: (value: V) => void;
  options: { value: V; label: ReactNode }[];
  size?: "sm" | "md";
}

export function SegmentedControl<V extends string>({ label, value, onChange, options, size = "md" }: Props<V>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (from: number, delta: number) => {
    const next = (from + delta + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(i, 1); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(i, -1); }
  };
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((o, i) => {
        const checked = o.value === value;
        return (
          <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={checked} tabIndex={checked ? 0 : -1}
            onClick={() => onChange(o.value)} onKeyDown={(e) => onKeyDown(e, i)}
            className={clsx("focus-ring whitespace-nowrap rounded-md font-medium transition-colors duration-fast ease-standard",
              size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
              checked ? "bg-surface text-content shadow-sm" : "text-content-muted hover:text-content")}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: Run and see them pass**

Run: `npx vitest run src/components/ui/Select.test.tsx src/components/ui/SegmentedControl.test.tsx` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/ui/Select.tsx src/components/ui/Select.test.tsx src/components/ui/SegmentedControl.tsx src/components/ui/SegmentedControl.test.tsx
git commit -m "feat(ui): accessible Select and SegmentedControl"
```

---

### Task 10: Tabs

**Files:**
- Create: `src/components/ui/Tabs.tsx`
- Test: create `src/components/ui/Tabs.test.tsx`

**Interfaces:**
- Produces: `Tabs<V extends string>({ label: string; tabs: { value: V; label: ReactNode; content: ReactNode; badge?: ReactNode }[]; value?: V; defaultValue?: V; onChange?: (v: V) => void })`. Controlled when `value` is given. Manual activation: arrow keys move focus, Enter/Space or click selects. Home/End jump to the ends.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/Tabs.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Tabs } from "./Tabs";

const tabs = [
  { value: "risk", label: "Top at risk", content: <p>Risk panel</p> },
  { value: "over", label: "Overstocked", content: <p>Over panel</p> },
  { value: "up", label: "Trending up", content: <p>Up panel</p> },
] as const;

it("follows the WAI-ARIA tabs pattern", () => {
  const onChange = vi.fn();
  render(<Tabs label="Inventory views" tabs={[...tabs]} onChange={onChange} />);
  expect(screen.getByRole("tablist", { name: "Inventory views" })).toBeInTheDocument();
  const first = screen.getByRole("tab", { name: "Top at risk" });
  expect(first).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel", { name: "Top at risk" })).toHaveTextContent("Risk panel");
  fireEvent.keyDown(first, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Overstocked" })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Overstocked" }), { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("over");
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Over panel");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Overstocked" }), { key: "End" });
  expect(screen.getByRole("tab", { name: "Trending up" })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("tab", { name: "Trending up" }), { key: "Home" });
  expect(first).toHaveFocus();
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/Tabs.test.tsx` → FAIL.

- [ ] **Step 3: Implement**

```tsx
// src/components/ui/Tabs.tsx
import clsx from "clsx";
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

interface Tab<V extends string> { value: V; label: ReactNode; content: ReactNode; badge?: ReactNode }
interface Props<V extends string> { label: string; tabs: Tab<V>[]; value?: V; defaultValue?: V; onChange?: (value: V) => void }

export function Tabs<V extends string>({ label, tabs, value, defaultValue, onChange }: Props<V>) {
  const base = useId();
  const [inner, setInner] = useState<V>(defaultValue ?? tabs[0].value);
  const current = value ?? inner;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const select = (v: V) => { if (value === undefined) setInner(v); onChange?.(v); };
  const focusAt = (i: number) => refs.current[(i + tabs.length) % tabs.length]?.focus();
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    const keys: Record<string, () => void> = {
      ArrowRight: () => focusAt(i + 1), ArrowLeft: () => focusAt(i - 1),
      Home: () => focusAt(0), End: () => focusAt(tabs.length - 1),
      Enter: () => select(tabs[i].value), " ": () => select(tabs[i].value),
    };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  };
  const active = tabs.find((t) => t.value === current) ?? tabs[0];
  return (
    <div className="min-w-0">
      <div role="tablist" aria-label={label} className="flex max-w-full gap-1 overflow-x-auto border-b border-line">
        {tabs.map((t, i) => {
          const selected = t.value === active.value;
          return (
            <button key={t.value} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`${base}-tab-${t.value}`}
              aria-selected={selected} aria-controls={`${base}-panel-${t.value}`} tabIndex={selected ? 0 : -1}
              onClick={() => select(t.value)} onKeyDown={(e) => onKeyDown(e, i)}
              className={clsx("focus-ring -mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-fast ease-standard",
                selected ? "border-accent text-content" : "border-transparent text-content-muted hover:text-content")}>
              {t.label}{t.badge}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${base}-panel-${active.value}`} aria-labelledby={`${base}-tab-${active.value}`} tabIndex={0} className="focus-ring pt-4">
        {active.content}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run and see it pass**

Run: `npx vitest run src/components/ui/Tabs.test.tsx` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/Tabs.tsx src/components/ui/Tabs.test.tsx
git commit -m "feat(ui): keyboard-accessible Tabs"
```

---

### Task 11: FilterBar

**Files:**
- Create: `src/components/ui/FilterBar.tsx`
- Test: create `src/components/ui/FilterBar.test.tsx`

**Interfaces:**
- Produces: `FilterBar({ label: string; filters: ReactNode; actions?: ReactNode; activeCount?: number; onClear?: () => void })`. Shows "Clear filters (n)" only when `activeCount > 0` and `onClear` is given.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/FilterBar.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

it("groups filters and offers clear only when filters are active", () => {
  const onClear = vi.fn();
  const { rerender } = render(<FilterBar label="Inventory filters" filters={<input aria-label="Search" />} actions={<button>Export</button>} activeCount={0} onClear={onClear} />);
  expect(screen.getByRole("toolbar", { name: "Inventory filters" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Clear filters/ })).not.toBeInTheDocument();
  rerender(<FilterBar label="Inventory filters" filters={<input aria-label="Search" />} activeCount={2} onClear={onClear} />);
  fireEvent.click(screen.getByRole("button", { name: "Clear filters (2)" }));
  expect(onClear).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/FilterBar.test.tsx` → FAIL.

- [ ] **Step 3: Implement**

```tsx
// src/components/ui/FilterBar.tsx
import type { ReactNode } from "react";
import { X } from "@/components/ui/icons";

export const FilterBar = ({ label, filters, actions, activeCount = 0, onClear }: {
  label: string; filters: ReactNode; actions?: ReactNode; activeCount?: number; onClear?: () => void;
}) => (
  <div role="toolbar" aria-label={label} className="flex min-w-0 flex-wrap items-end justify-between gap-3">
    <div className="flex min-w-0 max-w-full flex-1 items-end gap-2 overflow-x-auto pb-0.5 sm:flex-wrap sm:overflow-visible">
      {filters}
      {activeCount > 0 && onClear && (
        <button type="button" onClick={onClear} className="focus-ring inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-content-muted transition-colors duration-fast ease-standard hover:text-content">
          <X size={14} aria-hidden="true" />Clear filters ({activeCount})
        </button>
      )}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </div>
);
```

- [ ] **Step 4: Run and see it pass**

Run: `npx vitest run src/components/ui/FilterBar.test.tsx` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/FilterBar.tsx src/components/ui/FilterBar.test.tsx
git commit -m "feat(ui): FilterBar toolbar with clear-filters affordance"
```

---

### Task 12: Drawer with a shared dialog focus hook

**Files:**
- Create: `src/components/ui/useDialogFocus.ts`, `src/components/ui/Drawer.tsx`
- Modify: `src/components/ui/Modal.tsx` (use the hook; its behaviour is unchanged)
- Test: create `src/components/ui/Drawer.test.tsx`. The existing `Modal.test.tsx` and `Modal.wide.test.tsx` must stay green.

**Interfaces:**
- Produces:
  - `useDialogFocus(open: boolean, onClose: () => void, ref: RefObject<HTMLElement>): void`. Handles Escape, the Tab trap, body scroll lock, initial focus, and **restoring focus to the element that was focused before opening**.
  - `Drawer({ open: boolean; onClose: () => void; title: ReactNode; description?: ReactNode; children: ReactNode; footer?: ReactNode; width?: "md" | "lg" })`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/Drawer.test.tsx
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import { Drawer } from "./Drawer";

const Harness = () => {
  const [open, setOpen] = useState(false);
  return (<>
    <button onClick={() => setOpen(true)}>Open run history</button>
    <Drawer open={open} onClose={() => setOpen(false)} title="Run history" description="Last 20 runs">
      <button>First</button><button>Last</button>
    </Drawer>
  </>);
};

it("opens as a labelled modal dialog, traps Tab, closes on Escape and restores focus", async () => {
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Open run history" });
  trigger.focus();
  fireEvent.click(trigger);
  const dialog = screen.getByRole("dialog", { name: "Run history" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(dialog).toHaveAccessibleDescription("Last 20 runs");
  await act(() => new Promise((r) => requestAnimationFrame(() => r(null))));
  const last = screen.getByRole("button", { name: "Last" });
  last.focus();
  fireEvent.keyDown(window, { key: "Tab" });
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});
```

The close button is the first focusable element in the drawer, so a forward
Tab from "Last" wraps to "Close".

- [ ] **Step 2: Run and see it fail**

Run: `npx vitest run src/components/ui/Drawer.test.tsx` → FAIL.

- [ ] **Step 3: Extract the hook from Modal**

```ts
// src/components/ui/useDialogFocus.ts
import { useEffect, type RefObject } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/** Escape, Tab trap, scroll lock, initial focus and focus restore for modal surfaces. */
export function useDialogFocus(open: boolean, onClose: () => void, ref: RefObject<HTMLElement>) {
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !ref.current) return;
      const focusable = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.hasAttribute("disabled"));
      if (focusable.length === 0) { e.preventDefault(); return; }
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    const frame = requestAnimationFrame(() => {
      if (!ref.current) return;
      (ref.current.querySelector<HTMLElement>(FOCUSABLE) ?? ref.current).focus();
    });
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      cancelAnimationFrame(frame);
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [open, onClose, ref]);
}
```

In `src/components/ui/Modal.tsx`:
- Delete the `FOCUSABLE` constant and the whole `useEffect(() => { if (!open) return; ... }, [open, onClose]);` block.
- Add `import { useDialogFocus } from "./useDialogFocus";`.
- Right after `const titleId = useRef(...)`, call `useDialogFocus(open, onClose, dialogRef);`.
- Remove `useEffect` from the `react` import if nothing else uses it.

The one behaviour change is that Modal now restores focus on close, which the
spec requires.

- [ ] **Step 4: Implement Drawer**

```tsx
// src/components/ui/Drawer.tsx
import clsx from "clsx";
import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "@/components/ui/icons";
import { useDialogFocus } from "./useDialogFocus";

interface Props { open: boolean; onClose: () => void; title: ReactNode; description?: ReactNode; children: ReactNode; footer?: ReactNode; width?: "md" | "lg" }

export const Drawer = ({ open, onClose, title, description, children, footer, width = "md" }: Props) => {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();
  useDialogFocus(open, onClose, ref);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 animate-fade-in" onClick={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descId : undefined} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={clsx("drawer-panel flex h-full w-full flex-col border-l border-line bg-surface shadow-lg sm:w-auto", width === "lg" ? "sm:max-w-3xl sm:min-w-[40rem]" : "sm:max-w-xl sm:min-w-[28rem]")}>
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="t-section">{title}</h2>
            {description && <p id={descId} className="t-body mt-1">{description}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="focus-ring grid h-9 w-9 shrink-0 place-items-center rounded-lg text-content-muted hover:bg-surface-2 hover:text-content">
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
};
```

Add to `src/styles/index.css`, outside any `@layer` and before the
`prefers-reduced-motion` block (which already disables it for reduced-motion
users):

```css
@keyframes drawer-in { from { transform: translateX(24px); opacity: 0; } to { transform: none; opacity: 1; } }
.drawer-panel { animation: drawer-in var(--dur) var(--ease) both; }
```

- [ ] **Step 5: Run and see it pass**

Run: `npx vitest run src/components/ui/Drawer.test.tsx src/components/ui/Modal.test.tsx src/components/ui/Modal.wide.test.tsx src/components/ui/Controls.test.tsx` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/ui/useDialogFocus.ts src/components/ui/Drawer.tsx src/components/ui/Drawer.test.tsx src/components/ui/Modal.tsx src/styles/index.css
git commit -m "feat(ui): Drawer and shared dialog focus hook with focus restore"
```

---

### Task 13: Chart kit — axis formatters, tooltip, legend, frame

**Files:**
- Create: `src/components/charts/kit/axis.ts`, `src/components/charts/kit/ChartTooltip.tsx`, `src/components/charts/kit/ChartLegend.tsx`, `src/components/charts/kit/ChartFrame.tsx`, `src/components/charts/kit/index.ts`
- Test: create `src/components/charts/kit/axis.test.ts`, `src/components/charts/kit/ChartKit.test.tsx`

**Interfaces:**
- Consumes: `LoadingState`, `ErrorState`, `UnavailableState` (Task 5)
- Produces:
  - `formatDateTick(iso: string, granularity: "day" | "week" | "month"): string` → `"3 Aug"` / `"Aug 2026"`
  - `formatCompact(n: number): string` → `"1.2k"`, `"3.4M"`, `"950"`
  - `GRID_PROPS`, `AXIS_PROPS`: shared Recharts props (horizontal grid only, `var(--border)` stroke, 12px `var(--text-subtle)` ticks)
  - `type TooltipSeries = { key: string; label: string; kind: "actual" | "expected" | "range-low" | "range-high" | "other"; format?: (v: number) => string }`
  - `ChartTooltip({ active?: boolean; label?: string | number; payload?: { dataKey?: string | number; value?: number | null }[]; series: TooltipSeries[]; labelFormatter?: (l: string) => string; unit?: string })`: rows in the order actual, expected, range-low, range-high, other. A missing value shows "—".
  - `ChartLegend({ items: { label: string; color: string; style: "solid" | "dashed" | "band" }[] })`
  - `ChartFrame({ title: ReactNode; description?: ReactNode; controls?: ReactNode; legend?: ReactNode; height?: number; state?: "ready" | "loading" | "empty" | "error"; emptyTitle?: string; emptyReason?: ReactNode; onRetry?: () => void; children: ReactNode })`

- [ ] **Step 1: Write the failing tests**

```ts
// src/components/charts/kit/axis.test.ts
import { expect, it } from "vitest";
import { formatCompact, formatDateTick } from "./axis";

it("formats date ticks by granularity in UTC", () => {
  expect(formatDateTick("2026-08-03", "day")).toBe("3 Aug");
  expect(formatDateTick("2026-08-03", "week")).toBe("3 Aug");
  expect(formatDateTick("2026-08-01", "month")).toBe("Aug 2026");
});

it("compacts large numbers without inventing precision", () => {
  expect(formatCompact(950)).toBe("950");
  expect(formatCompact(1200)).toBe("1.2k");
  expect(formatCompact(3_400_000)).toBe("3.4M");
  expect(formatCompact(0)).toBe("0");
});
```

```tsx
// src/components/charts/kit/ChartKit.test.tsx
import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { ChartFrame, ChartLegend, ChartTooltip } from "./index";

it("orders tooltip rows actual, expected, low, high and dashes missing values", () => {
  render(<ChartTooltip active label="2026-11-02" unit="units"
    series={[
      { key: "p90", label: "Upper (P90)", kind: "range-high" },
      { key: "p50", label: "Expected", kind: "expected" },
      { key: "actual", label: "Actual", kind: "actual" },
      { key: "p10", label: "Lower (P10)", kind: "range-low" },
    ]}
    payload={[{ dataKey: "p90", value: 30 }, { dataKey: "p50", value: 20 }, { dataKey: "actual", value: null }, { dataKey: "p10", value: 10 }]} />);
  const rows = screen.getAllByRole("listitem").map((li) => li.textContent);
  expect(rows).toEqual(["Actual—", "Expected20 units", "Lower (P10)10 units", "Upper (P90)30 units"]);
});

it("renders nothing when inactive", () => {
  const { container } = render(<ChartTooltip active={false} series={[]} payload={[]} />);
  expect(container).toBeEmptyDOMElement();
});

it("names legend styles in text, not color alone", () => {
  render(<ChartLegend items={[{ label: "Actual", color: "var(--chart-actual)", style: "solid" }, { label: "Expected", color: "var(--chart-forecast)", style: "dashed" }]} />);
  const list = screen.getByRole("list", { name: "Legend" });
  expect(within(list).getByText("Actual")).toBeInTheDocument();
  expect(within(list).getByText("Expected")).toBeInTheDocument();
});

it("swaps the plot for loading, empty and error states at a fixed height", () => {
  const { rerender } = render(<ChartFrame title="Demand" state="loading"><div>plot</div></ChartFrame>);
  expect(screen.getByRole("status")).toBeInTheDocument();
  rerender(<ChartFrame title="Demand" state="empty" emptyTitle="No sales yet" emptyReason="Import sales to see demand."><div>plot</div></ChartFrame>);
  expect(screen.getByText("No sales yet")).toBeInTheDocument();
  rerender(<ChartFrame title="Demand" state="error"><div>plot</div></ChartFrame>);
  expect(screen.getByRole("alert")).toBeInTheDocument();
  rerender(<ChartFrame title="Demand"><div>plot</div></ChartFrame>);
  expect(screen.getByText("plot")).toBeInTheDocument();
  expect(screen.getByRole("figure", { name: "Demand" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and see them fail**

Run: `npx vitest run src/components/charts/kit` → FAIL.

- [ ] **Step 3: Implement axis.ts**

```ts
// src/components/charts/kit/axis.ts
const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

export function formatDateTick(iso: string, granularity: "day" | "week" | "month"): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return (granularity === "month" ? MONTH : DAY).format(d);
}

export function formatCompact(n: number): string {
  const abs = Math.abs(n);
  const trim = (v: number) => String(Number(v.toFixed(1)));
  if (abs >= 1_000_000) return `${trim(n / 1_000_000)}M`;
  if (abs >= 1_000) return `${trim(n / 1_000)}k`;
  return String(n);
}

export const GRID_PROPS = { vertical: false, stroke: "var(--border)", strokeDasharray: "0" } as const;
export const AXIS_PROPS = { tick: { fontSize: 12, fill: "var(--text-subtle)" }, tickLine: false, axisLine: false } as const;
```

`--text-subtle` and `--border` are plain `rgb(...)` colors in both themes
(`index.css:40,42,85,87`). Never pass a `--*-rgb` channel directly as a color;
the pass-1 QA log records that bug.

- [ ] **Step 4: Implement ChartTooltip, ChartLegend, ChartFrame and the index**

```tsx
// src/components/charts/kit/ChartTooltip.tsx
export type TooltipSeries = { key: string; label: string; kind: "actual" | "expected" | "range-low" | "range-high" | "other"; format?: (v: number) => string };

const ORDER: Record<TooltipSeries["kind"], number> = { actual: 0, expected: 1, "range-low": 2, "range-high": 3, other: 4 };

interface Props {
  active?: boolean;
  label?: string | number;
  payload?: { dataKey?: string | number; value?: number | null }[];
  series: TooltipSeries[];
  labelFormatter?: (label: string) => string;
  unit?: string;
}

export const ChartTooltip = ({ active, label, payload, series, labelFormatter, unit }: Props) => {
  if (!active || !payload) return null;
  const values = new Map(payload.map((p) => [String(p.dataKey), p.value]));
  const rows = [...series].sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);
  return (
    <div className="min-w-44 rounded-xl border border-line bg-surface px-3 py-2.5 text-xs shadow-md">
      {label !== undefined && <p className="mb-1.5 font-medium text-content">{labelFormatter ? labelFormatter(String(label)) : label}</p>}
      <ul className="space-y-1">
        {rows.map((s) => {
          const v = values.get(s.key);
          const shown = v === null || v === undefined ? "—" : `${s.format ? s.format(v) : v.toLocaleString("en-IN")}${unit ? ` ${unit}` : ""}`;
          return <li key={s.key} className="flex justify-between gap-4"><span className="text-content-muted">{s.label}</span><span className="tabular-nums font-medium text-content">{shown}</span></li>;
        })}
      </ul>
    </div>
  );
};
```

```tsx
// src/components/charts/kit/ChartLegend.tsx
export const ChartLegend = ({ items }: { items: { label: string; color: string; style: "solid" | "dashed" | "band" }[] }) => (
  <ul aria-label="Legend" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-content-muted">
    {items.map((i) => (
      <li key={i.label} className="inline-flex items-center gap-1.5">
        {i.style === "band"
          ? <span aria-hidden="true" className="h-2.5 w-4 rounded-sm opacity-30" style={{ background: i.color }} />
          : <span aria-hidden="true" className="w-4 border-t-2" style={{ borderColor: i.color, borderStyle: i.style === "dashed" ? "dashed" : "solid" }} />}
        {i.label}
      </li>
    ))}
  </ul>
);
```

```tsx
// src/components/charts/kit/ChartFrame.tsx
import { useId, type ReactNode } from "react";
import { ErrorState, LoadingState, UnavailableState } from "@/components/ui/StateViews";

interface Props {
  title: ReactNode; description?: ReactNode; controls?: ReactNode; legend?: ReactNode; height?: number;
  state?: "ready" | "loading" | "empty" | "error"; emptyTitle?: string; emptyReason?: ReactNode; onRetry?: () => void; children: ReactNode;
}

/** Fixed-height plot area so state changes never shift the layout. */
export const ChartFrame = ({ title, description, controls, legend, height = 300, state = "ready", emptyTitle = "Nothing to chart yet", emptyReason = "There is no recorded data for this view.", onRetry, children }: Props) => {
  const titleId = useId();
  return (
    <figure aria-labelledby={titleId} className="min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={titleId} className="t-card">{title}</h3>
          {description && <p className="mt-1 text-xs text-content-subtle">{description}</p>}
        </div>
        {controls && <div className="flex flex-wrap items-center gap-2">{controls}</div>}
      </div>
      <div style={{ height }} className="grid min-w-0">
        {state === "loading" ? <LoadingState variant="chart" label="Loading chart" />
          : state === "error" ? <div className="self-center"><ErrorState onRetry={onRetry} /></div>
          : state === "empty" ? <div className="self-center"><UnavailableState title={emptyTitle} reason={emptyReason} /></div>
          : children}
      </div>
      {legend && state === "ready" && <figcaption className="mt-3">{legend}</figcaption>}
    </figure>
  );
};
```

```ts
// src/components/charts/kit/index.ts
export { AXIS_PROPS, GRID_PROPS, formatCompact, formatDateTick } from "./axis";
export { ChartTooltip, type TooltipSeries } from "./ChartTooltip";
export { ChartLegend } from "./ChartLegend";
export { ChartFrame } from "./ChartFrame";
```

- [ ] **Step 5: Run and see them pass**

Run: `npx vitest run src/components/charts/kit` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/charts/kit
git commit -m "feat(charts): shared chart kit — axis formatters, ordered tooltip, legend, stateful frame"
```

---

### Task 14: Document the kit and verify the whole plan

**Files:**
- Modify: `frontend/DESIGN.md` (append a "Components" section)

- [ ] **Step 1: Append to `frontend/DESIGN.md`**

```markdown
## Components

Use the shared kit before writing page-local UI. All live in `src/components/ui/` unless noted.

| Need | Use | Notes |
|---|---|---|
| A KPI | `MetricTile` | `provenance` is required: recorded, estimated, forecast or heuristic. `null` shows "—" plus a reason. `KPICard` is a legacy adapter. |
| A table | `DataTable` (`Table`) | `sortValue` per column, `loading`, `density`, `maxHeight`, `mobile="cards"` with column `priority`, `selection` only where bulk actions exist, `caption`. |
| Filters | `FilterBar` + `Select` / `SegmentedControl` | Native select. Segmented control for 2–5 views. |
| Views on one page | `Tabs` | WAI-ARIA tabs; arrow keys move focus, Enter selects. |
| Grouping without a card | `Section` | Heading, hairline divider, actions. |
| Loading, error, unavailable | `LoadingState`, `ErrorState`, `UnavailableState`, `QueryBoundary` | Never render 0 for missing data. |
| Detail or history panel | `Drawer` | Shares focus handling with `Modal` (`useDialogFocus`). |
| A chart | `components/charts/kit`: `ChartFrame`, `ChartTooltip`, `ChartLegend`, `AXIS_PROPS`, `GRID_PROPS` | Tooltip order: actual, expected, lower, upper. |
| Type | `.t-page .t-section .t-card .t-kpi .t-label .t-body .t-table` | Instead of `text-[Npx]`. |
| Motion | `duration-fast` (140ms), `duration-base` (200ms), `ease-standard` | Reduced motion is handled globally. |
```

- [ ] **Step 2: Run every check**

From `frontend/`:

```bash
npx tsc --noEmit
npx eslint src --ext .ts,.tsx
npx vitest run
npm run build
```

Expected:
- `tsc`: no output.
- `eslint`: no errors in files this plan created or modified. Compare with
  the baseline from `git stash; npx eslint src --ext .ts,.tsx | tail -3; git stash pop`
  run before starting. Pre-existing errors elsewhere are noted, not fixed.
- `vitest`: all files pass. 80 files from Task 2 plus 13 new test files
  (HybridRoute, foundation-tokens, StateViews, Section, MetricTile, Table,
  Select, SegmentedControl, Tabs, FilterBar, Drawer, axis, ChartKit) = 93.
- `build`: succeeds. Record the size of the main `index-*.js` chunk and compare
  it with the build at `7e47945`. Expected change: within ±5kB.

- [ ] **Step 3: Browser check**

With the `sanket-frontend` preview running:
- `/e2e/review.html?screen=SalesAnalytics`, `?screen=Inventory`, `?screen=HybridForecasts` render inside the shell.
- In the real app (`http://localhost:5173/workspace`, signed in), the sidebar shows "Hybrid Forecasts" under Plan, it opens `/workspace/forecasts/hybrid`, and only that entry is highlighted as active.
- Ctrl K → type "hyb" → the entry is shown.

- [ ] **Step 4: Commit**

```bash
git add DESIGN.md
git commit -m "docs(design): component kit usage table"
```
