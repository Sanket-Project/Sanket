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
