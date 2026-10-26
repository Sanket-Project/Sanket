import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSidebarStore } from "@/stores/sidebar";

vi.mock("@/api/decisions", () => ({ decisionsApi: { list: vi.fn().mockResolvedValue({ decisions: [] }) } }));
vi.mock("@/api/build", () => ({ buildApi: { info: vi.fn().mockResolvedValue(null) }, shortSha: (s: string) => s }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));

import { Sidebar } from "@/components/layout/Sidebar";

// Deep audit F10/F11: the mobile drawer let Tab escape into the obscured page,
// left focus on the trigger, kept closed navigation in the tab order, and used
// white-on-white search styling.

function setViewport(desktop: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: desktop && query.includes("min-width"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
}

function Harness() {
  const toggle = useSidebarStore((s) => s.toggleMobile);
  return (
    <>
      <Sidebar />
      <div id="app-main-column">
        <button type="button" onClick={toggle}>Open navigation</button>
        <button type="button">Currency</button>
      </div>
    </>
  );
}

const renderHarness = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><Harness /></MemoryRouter>
    </QueryClientProvider>,
  );

// Selected directly: an aria-hidden landmark has no computed accessible name.
const drawer = () => {
  const aside = document.querySelector<HTMLElement>('aside[aria-label="Main navigation"]');
  if (!aside) throw new Error("navigation landmark not rendered");
  return aside;
};

async function openDrawer() {
  const opener = screen.getByRole("button", { name: "Open navigation" });
  opener.focus();
  fireEvent.click(opener);
  await waitFor(() => expect(screen.getByRole("searchbox", { name: "Search navigation" })).toHaveFocus());
  return opener;
}

describe("Sidebar mobile drawer", () => {
  beforeEach(() => {
    setViewport(false);
    useSidebarStore.setState({ mobileOpen: false, collapsed: false });
  });
  afterEach(() => act(() => useSidebarStore.setState({ mobileOpen: false })));

  it("keeps closed navigation out of the keyboard and accessibility trees", () => {
    renderHarness();
    expect(drawer()).toHaveAttribute("inert");
    expect(drawer()).toHaveAttribute("aria-hidden", "true");
  });

  it("moves focus into the drawer and makes the page behind it inert", async () => {
    renderHarness();
    await openDrawer();
    expect(drawer()).not.toHaveAttribute("inert");
    expect(document.getElementById("app-main-column")).toHaveAttribute("inert");
  });

  it("keeps Tab inside the open drawer", async () => {
    renderHarness();
    await openDrawer();
    const focusables = drawer().querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input");
    const last = focusables[focusables.length - 1];
    last.focus();

    fireEvent.keyDown(drawer(), { key: "Tab" });
    expect(focusables[0]).toHaveFocus();

    fireEvent.keyDown(drawer(), { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
  });

  it("wraps from the last VISIBLE control even when hidden controls follow it", async () => {
    // Found in a real browser: the desktop-only Collapse button is display:none
    // on mobile, so focus never reached the DOM-last control and escaped.
    const original = HTMLElement.prototype.checkVisibility;
    HTMLElement.prototype.checkVisibility = function () {
      return !/collapse sidebar|expand sidebar/i.test(this.getAttribute("aria-label") ?? "");
    };
    try {
      renderHarness();
      await openDrawer();
      const visible = Array.from(drawer().querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input"))
        .filter((el) => el.checkVisibility());
      visible[visible.length - 1].focus();

      fireEvent.keyDown(drawer(), { key: "Tab" });

      expect(visible[0]).toHaveFocus();
    } finally {
      HTMLElement.prototype.checkVisibility = original;
    }
  });

  it("still skips hidden controls where checkVisibility is unavailable (older Safari)", async () => {
    const original = HTMLElement.prototype.checkVisibility;
    const rects = HTMLElement.prototype.getClientRects;
    // @ts-expect-error -- simulate a browser without checkVisibility
    delete HTMLElement.prototype.checkVisibility;
    HTMLElement.prototype.getClientRects = function () {
      const hidden = /collapse sidebar|expand sidebar/i.test(this.getAttribute("aria-label") ?? "");
      return (hidden ? [] : [{}]) as unknown as DOMRectList;
    };
    try {
      renderHarness();
      await openDrawer();
      const visible = Array.from(drawer().querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input"))
        .filter((el) => el.getClientRects().length > 0);
      visible[visible.length - 1].focus();

      fireEvent.keyDown(drawer(), { key: "Tab" });

      expect(visible[0]).toHaveFocus();
    } finally {
      HTMLElement.prototype.checkVisibility = original;
      HTMLElement.prototype.getClientRects = rects;
    }
  });

  it("closes on Escape and returns focus to the opener", async () => {
    renderHarness();
    const opener = await openDrawer();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(opener).toHaveFocus());
    expect(drawer()).toHaveAttribute("inert");
    expect(document.getElementById("app-main-column")).not.toHaveAttribute("inert");
  });

  it("offers a close control inside the drawer", async () => {
    renderHarness();
    await openDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(useSidebarStore.getState().mobileOpen).toBe(false);
  });

  it("is never inert on desktop", () => {
    setViewport(true);
    renderHarness();
    expect(drawer()).not.toHaveAttribute("inert");
    expect(drawer()).not.toHaveAttribute("aria-hidden");
  });
});

describe("Sidebar search copy (deep audit F16)", () => {
  beforeEach(() => setViewport(true));

  it("describes what it searches and shows the Windows shortcut", () => {
    vi.spyOn(navigator, "platform", "get").mockReturnValue("Win32");
    renderHarness();
    const search = screen.getByRole("searchbox", { name: "Search navigation" });
    expect(search).toHaveAttribute("placeholder", "Find a page…");
    expect(screen.getByText("Ctrl K")).toBeInTheDocument();
  });

  it("uses theme tokens for the search field so it is legible on the light drawer", () => {
    renderHarness();
    const search = screen.getByRole("searchbox", { name: "Search navigation" });
    expect(search.className).toMatch(/(^|\s)text-content(\s|$)/);
    expect(search.className).not.toMatch(/(^|\s)text-white(\s|$)/);
    expect(search.className).toMatch(/lg:text-white/);
  });
});
