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
