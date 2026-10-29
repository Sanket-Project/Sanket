import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import { Drawer } from "./Drawer";
import { Modal } from "./Modal";

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

const raf = () => act(() => new Promise((r) => requestAnimationFrame(() => r(null))));

it("keeps focus in the dialog when the parent re-renders with a new onClose", async () => {
  const Typing = () => {
    const [open, setOpen] = useState(false);
    const [text, setText] = useState("");
    return (<>
      <button onClick={() => setOpen(true)}>Open typing</button>
      <Drawer open={open} onClose={() => setOpen(false)} title="Edit">
        <input aria-label="Name" value={text} onChange={(e) => setText(e.target.value)} />
      </Drawer>
    </>);
  };
  render(<Typing />);
  fireEvent.click(screen.getByRole("button", { name: "Open typing" }));
  await raf();
  const input = screen.getByLabelText("Name");
  input.focus();
  fireEvent.change(input, { target: { value: "abc" } });
  await raf();
  expect(screen.getByLabelText("Name")).toHaveFocus();
  expect(document.body.style.overflow).toBe("hidden");
});

it("restores the previous body overflow on close", async () => {
  document.body.style.overflow = "scroll";
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "Open run history" }));
  await raf();
  expect(document.body.style.overflow).toBe("hidden");
  fireEvent.keyDown(window, { key: "Escape" });
  expect(document.body.style.overflow).toBe("scroll");
  document.body.style.overflow = "";
});

it("with a modal stacked on a drawer, Escape closes only the top surface", async () => {
  document.body.style.overflow = "auto";
  const Stacked = () => {
    const [drawer, setDrawer] = useState(false);
    const [modal, setModal] = useState(false);
    return (<>
      <button onClick={() => setDrawer(true)}>Open drawer</button>
      <Drawer open={drawer} onClose={() => setDrawer(false)} title="Run history">
        <button onClick={() => setModal(true)}>Delete run</button>
        <Modal open={modal} onClose={() => setModal(false)} title="Confirm delete"><button>Yes</button></Modal>
      </Drawer>
    </>);
  };
  render(<Stacked />);
  fireEvent.click(screen.getByRole("button", { name: "Open drawer" }));
  await raf();
  const opener = screen.getByRole("button", { name: "Delete run" });
  opener.focus();
  fireEvent.click(opener);
  await raf();
  expect(screen.getByRole("dialog", { name: "Confirm delete" })).toBeInTheDocument();
  expect(document.body.style.overflow).toBe("hidden");

  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog", { name: "Confirm delete" })).not.toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "Run history" })).toBeInTheDocument();
  expect(opener).toHaveFocus();
  expect(document.body.style.overflow).toBe("hidden");

  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe("auto");
  document.body.style.overflow = "";
});
