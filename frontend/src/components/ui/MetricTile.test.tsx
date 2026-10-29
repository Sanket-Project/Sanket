import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { MetricTile } from "./MetricTile";

it("labels where the number comes from", () => {
  render(<MetricTile label="Items sold" value="1,240" provenance="recorded" />);
  expect(screen.getByText("Recorded")).toBeInTheDocument();
  expect(screen.getByText("1,240")).toBeInTheDocument();
});

it("keeps an observed zero as 0", () => {
  render(<MetricTile label="Stockouts" value={0} provenance="recorded" />);
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.queryByText("—")).not.toBeInTheDocument();
});

it("shows a dash and the reason when the value is missing, never 0", () => {
  render(<MetricTile label="Revenue at risk" value={null} provenance="estimated" unavailableReason="No prices imported" />);
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("No prices imported")).toBeInTheDocument();
  expect(screen.queryByText("0")).not.toBeInTheDocument();
});

it("falls back to a generic reason when none is given", () => {
  render(<MetricTile label="Coverage" value={undefined} provenance="heuristic" />);
  expect(screen.getByText("Not available from current data")).toBeInTheDocument();
});

it("becomes a link when given href", () => {
  render(<MemoryRouter><MetricTile label="Open decisions" value={3} provenance="recorded" href="/workspace/decisions" /></MemoryRouter>);
  expect(screen.getByRole("link", { name: /Open decisions/ })).toHaveAttribute("href", "/workspace/decisions");
});

it("shows a tone dot when a tone is set and there is no icon", () => {
  const { container } = render(<MetricTile label="At risk" value={2} provenance="recorded" tone="warning" />);
  expect(container.querySelector(".bg-amber-500")).not.toBeNull();
});

it("shows no tone dot for the default tone", () => {
  const { container } = render(<MetricTile label="At risk" value={2} provenance="recorded" />);
  expect(container.querySelector(".bg-amber-500, .bg-rose-500, .bg-emerald-500")).toBeNull();
});
