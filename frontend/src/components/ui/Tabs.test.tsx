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

it("only the selected tab carries aria-controls, pointing at the panel", () => {
  render(<Tabs label="Inventory views" tabs={[...tabs]} />);
  const active = screen.getByRole("tab", { name: "Top at risk" });
  const inactive = screen.getByRole("tab", { name: "Overstocked" });
  expect(inactive).not.toHaveAttribute("aria-controls");
  expect(screen.getByRole("tab", { name: "Trending up" })).not.toHaveAttribute("aria-controls");
  expect(active).toHaveAttribute("aria-controls", screen.getByRole("tabpanel").id);
});
