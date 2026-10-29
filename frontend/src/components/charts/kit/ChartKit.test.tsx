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
