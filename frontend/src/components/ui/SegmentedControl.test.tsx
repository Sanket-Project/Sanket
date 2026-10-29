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
