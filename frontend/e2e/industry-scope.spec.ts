import { execFileSync } from "node:child_process";
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The industry boundary, end to end.
 *
 * Creates a real Fashion workspace through the real signup form, then checks
 * both halves of the boundary: that the Fashion experience works, and that
 * every route into another industry is closed — the navigation, a typed URL,
 * and the API underneath. The last of those is the one that matters; the first
 * two only stop an honest user tripping over it.
 */

const stamp = Date.now();
const slug = `e2e-fashion-${stamp}`;
const email = `owner@${slug}.example.com`;
const password = "Sup3rSecret!";

const devToken = (page: Page) =>
  page.evaluate(() => localStorage.getItem("sanket.dev.token"));

/**
 * Give the new workspace a live subscription.
 *
 * Not incidental setup. Every workspace router is behind the paywall, so an
 * unsubscribed workspace sees "Activate Your SANKET Workspace" on *every* route
 * — including the Pharma one. That is a denial, but for the wrong reason: it
 * would pass this test while telling us nothing about the industry boundary.
 * A real customer asking "can I reach Pharma?" is a paying one.
 *
 * Seeded through the database because the real path runs through Razorpay.
 * Matches the local-dev-stack assumption the other specs already make.
 */
function grantSubscription(workspaceSlug: string) {
  const sql = `
    INSERT INTO subscriptions (id, tenant_id, plan_id, status,
                               current_period_start, current_period_end,
                               cancel_at_period_end, metadata)
    SELECT gen_random_uuid(), id, 'enterprise_monthly', 'active',
           now() - interval '1 day', now() + interval '365 days', FALSE, '{}'::jsonb
    FROM tenants WHERE slug = '${workspaceSlug}'`;
  execFileSync(
    "docker",
    ["compose", "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "sanket", "-c", sql],
    { cwd: "..", stdio: "pipe" },
  );
}

async function completeOnboarding(request: APIRequestContext, token: string) {
  // Drive the wizard's own endpoint rather than clicking through five steps
  // that upload files and run a baseline forecast. What this journey is about
  // starts once setup is done.
  const res = await request.put("/api/v1/onboarding/state", {
    headers: { Authorization: `Bearer ${token}` },
    data: { status: "complete", current_step: "done" },
  });
  expect(res.status()).toBe(200);
}

test.describe("industry-scoped workspace", () => {
  test("a Fashion workspace can reach Fashion and nothing else", async ({
    page,
    request,
  }) => {
    // ── 1. Create a Fashion workspace ────────────────────────────────────────
    await page.goto("/login?mode=signup");
    await page.fill("#signup-name", "E2E Owner");
    await page.fill("#signup-workspace", slug);
    await page.fill("#signup-email", email);
    await page.fill("#signup-password", password);
    await page.fill("#signup-confirm-password", password);

    // The industry is required — submitting without it must not create anything.
    await page.click('form[aria-label="Create account form"] button[type="submit"]');
    await expect(page.getByText(/choose the industry/i)).toBeVisible();

    await page.getByRole("radio", { name: /apparel & fashion/i }).click();
    await page.click('form[aria-label="Create account form"] button[type="submit"]');

    // ── 2. The permitted onboarding flow ─────────────────────────────────────
    await page.waitForURL("**/onboarding", { timeout: 20000 });
    await expect(page.getByText(/apparel & fashion/i).first()).toBeVisible();

    const token = await devToken(page);
    expect(token, "dev-mode bearer should be persisted after signup").toBeTruthy();
    await completeOnboarding(request, token!);
    grantSubscription(slug);

    // ── 3. The Fashion experience loads ──────────────────────────────────────
    await page.goto("/workspace");
    await expect(page.locator("aside")).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("Fashion & Apparel").first()).toBeVisible();

    // ── 4. No other industry is navigable ────────────────────────────────────
    for (const other of [
      /pharmaceuticals/i,
      /agrocenter/i,
      /consumer electronics/i,
      /tools & hardware/i,
    ]) {
      await expect(page.getByText(other)).toHaveCount(0);
    }
    await expect(page.getByText(/switch industry/i)).toHaveCount(0);

    // ── 5. A typed Pharma URL is denied ──────────────────────────────────────
    await page.goto("/workspace/pharma/batches");
    await expect(
      page.getByText(/not available for this workspace/i),
    ).toBeVisible({ timeout: 20000 });

    // ── 6. The Pharma API is denied ──────────────────────────────────────────
    const denied = await request.get("/api/v1/pharma/overview", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(denied.status()).toBe(403);

    // Sending the old switching header does not help either.
    const header = await request.get("/api/v1/industry/context", {
      headers: { Authorization: `Bearer ${token}`, "X-Industry-Code": "pharma" },
    });
    expect(header.status()).toBe(403);

    // ── 7. An invited teammate inherits Fashion ──────────────────────────────
    const invite = await request.post("/api/v1/invites", {
      headers: { Authorization: `Bearer ${token}` },
      data: { email: `mate-${stamp}@invite.example.com`, role: "analyst" },
    });
    expect(invite.status()).toBe(201);
    const inviteToken = (await invite.json()).invite_url.split("token=")[1];

    const accepted = await request.post("/api/v1/auth/accept-invite", {
      data: {
        token: inviteToken,
        name: "Team Mate",
        password: "An0therSecret!",
      },
    });
    expect(accepted.status()).toBe(201);
    const member = await accepted.json();
    expect(member.active_industry).toBe("fashion");
    expect(member.role).toBe("analyst");
  });

  test("the public landing page offers all four entry points", async ({ page }) => {
    await page.goto("/");
    // The intro loader gates the page on first visit in a session.
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("button", { name: /sign in/i }).first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: /create workspace/i }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /request enterprise demo/i }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /try live sandbox/i }).first(),
    ).toBeVisible();
  });
});
