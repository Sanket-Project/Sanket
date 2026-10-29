import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ForecastChangeExplanation } from "./ForecastChangeExplanation";

it("labels hand-set trend shifts as unvalidated scenarios rather than demand causes", () => {
  render(<ForecastChangeExplanation explanation={{ median_shift_pct: 0.1, band_change_pct: 0, baseline_band_mean: 1, adjusted_band_mean: 1.1, drivers: [] }} sampleCount={10} dataSource="chronos_zero_shot" />);
  expect(screen.getByText("Trend adjustment scenario")).toBeInTheDocument();
  expect(screen.getByText(/have not been validated to improve accuracy/)).toBeInTheDocument();
  expect(screen.queryByText("Forecast drivers")).not.toBeInTheDocument();
});
