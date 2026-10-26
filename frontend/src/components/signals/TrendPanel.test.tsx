import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendPanel } from "@/components/signals/TrendPanel";
import type { TrendScore } from "@/types/api";

const base: TrendScore = {
  industry: "fashion",
  score: 0,
  volatility: null,
  sample_count: 0,
  by_kind: {},
  drivers: [],
  horizon_days: 90,
  as_of: "2026-10-26T09:00:00Z",
};

describe("TrendPanel (Hybrid forecasts, audit F05)", () => {
  it("says no signal adjustment was possible instead of 'they mostly agree'", () => {
    render(<TrendPanel score={{ ...base, evidence: {
      status: "unavailable", sample_count: 0, source_count: 0, newest_sample_at: null,
      lookback_hours: 168, min_samples: 3, stale_after_hours: 48, agreement_reportable: false,
      last_ingest: null, message: "No signal samples in the last 168 hours." } }} />);

    expect(screen.getByText(/no signal adjustment/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/mostly agree|somewhat mixed/i);
  });

  it("still reports agreement when there is evidence", () => {
    render(<TrendPanel score={{ ...base, score: 0.3, volatility: 0.1, sample_count: 6 }} />);
    expect(screen.getByText(/they mostly agree/i)).toBeInTheDocument();
  });
});
