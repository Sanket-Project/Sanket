import { act, render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ScrollManager } from "@/components/layout/ScrollManager";

// Deep audit F15: <main> is a persistent scroll container, so a new page
// opened at the previous page's scroll offset, below its own heading.

let go: ReturnType<typeof useNavigate>;
function Page() {
  go = useNavigate();
  return null;
}

function setup() {
  // MemoryRouter, like the app's BrowserRouter (data routers' Request-based
  // navigation does not run under jsdom).
  render(
    <MemoryRouter initialEntries={["/workspace/inventory"]}>
      <main id="main-content" />
      <ScrollManager />
      <Page />
    </MemoryRouter>,
  );
  const main = document.getElementById("main-content") as HTMLElement;
  return { main };
}

describe("ScrollManager", () => {
  it("opens a newly visited page at the top", async () => {
    const { main } = setup();
    main.scrollTop = 640;

    await act(async () => go("/workspace/decisions"));

    expect(main.scrollTop).toBe(0);
  });

  it("restores the previous position on Back", async () => {
    const { main } = setup();
    main.scrollTop = 640;
    await act(async () => go("/workspace/decisions"));
    main.scrollTop = 120;

    await act(async () => go(-1));

    expect(main.scrollTop).toBe(640);
  });

  it("keeps the position when only the query string changes", async () => {
    const { main } = setup();
    main.scrollTop = 300;

    await act(async () => go("/workspace/inventory?q=boduppal"));

    expect(main.scrollTop).toBe(300);
  });
});
