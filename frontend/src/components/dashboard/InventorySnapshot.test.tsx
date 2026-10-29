import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { InventorySnapshot } from "./InventorySnapshot";
import type { SkuCoverage } from "@/api/inventory";

const sku = (status: SkuCoverage["sku_wide"]["status"]): SkuCoverage => ({
  sku_id: status, sku_code: `SKU-${status}`, lead_time_days: 14, lead_time_assumed: false,
  demand: { basis: "forecast", weekly_units: 10, run_id: "test", reason: "Saved forecast" },
  sku_wide: { available_units: 20, inbound_units: 0, cover_days: 14, status, reason: "Recorded coverage" }, locations: [],
});

it("shows only source-backed risks and keeps missing confidence unknown", () => {
  render(<MemoryRouter><InventorySnapshot skus={[sku("critical"), sku("healthy"), sku("excess")]} /></MemoryRouter>);
  expect(screen.getByRole("link", { name: "SKU-critical" })).toHaveAttribute("href", "/workspace/skus/critical");
  expect(screen.queryByText("SKU-healthy")).not.toBeInTheDocument();
  expect(screen.getByText("Not scored")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Overstock" }));
  expect(screen.getByRole("link", { name: "SKU-excess" })).toBeInTheDocument();
});

it("keeps an unavailable source distinct from a verified empty risk list", () => {
  render(<MemoryRouter><InventorySnapshot unavailable /></MemoryRouter>);
  expect(screen.getByText(/Stock coverage unavailable/)).toBeInTheDocument();
  expect(screen.queryByText(/No at-risk stock/)).not.toBeInTheDocument();
});
