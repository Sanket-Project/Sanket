import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ForecastEngine } from "@/pages/landing/sections/ForecastEngine";

/**
 * Audit F08: the landing page promised "a usable curve for a SKU that has
 * never been sold". The zero-shot path needs eight weeks of a SKU's history;
 * a never-sold SKU is reported as not forecast. The copy must say so.
 */
describe("ForecastEngine landing copy", () => {
  it("does not promise forecasts for products with no sales history", () => {
    render(<ForecastEngine />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/never been sold.*usable curve|forecast without history/i);
    expect(screen.getByText(/never sold gets no forecast curve/i)).toBeInTheDocument();
  });

  it("states the history a forecast needs and does not claim per-SKU model routing", () => {
    render(<ForecastEngine />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/eight weeks/i);
    expect(text).not.toMatch(/routed to the approach/i);
  });
});
