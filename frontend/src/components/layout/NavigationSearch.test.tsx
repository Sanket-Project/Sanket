import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { NavigationSearch } from "./NavigationSearch";
import { useSidebarStore } from "@/stores/sidebar";

it("opens the real navigation finder on small screens", () => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
  useSidebarStore.setState({ collapsed: true, mobileOpen: false });
  render(<NavigationSearch />);
  fireEvent.click(screen.getByRole("button", { name: "Find a page" }));
  expect(useSidebarStore.getState().collapsed).toBe(false);
  expect(useSidebarStore.getState().mobileOpen).toBe(true);
});
