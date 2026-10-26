import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendScoreGauge } from "@/pages/TrendAnalysis";
import type { TrendEvidence, TrendScore } from "@/types/api";

/**
 * Audit F05: with zero signal samples the gauge said "Demand looks stable" and
 * "High (100%)" agreement, because an empty score defaults to volatility 0.
 */
const evidence = (over: Partial<TrendEvidence>): TrendEvidence => ({
  status: "available",
  sample_count: 5,
  source_count: 2,
  newest_sample_at: "2026-10-26T08:00:00Z",
  lookback_hours: 168,
  min_samples: 3,
  stale_after_hours: 48,
  agreement_reportable: true,
  last_ingest: null,
  message: "",
  ...over,
});

const score = (over: Partial<TrendScore>): TrendScore => ({
  industry: "fashion",
  score: 0,
  volatility: null,
  sample_count: 0,
  by_kind: {},
  drivers: [],
  horizon_days: 90,
  as_of: "2026-10-26T09:00:00Z",
  ...over,
});

const renderGauge = (s: TrendScore | undefined) =>
  render(<TrendScoreGauge score={s} loading={false} industry="fashion" />);

describe("TrendScoreGauge evidence (audit F05)", () => {
  it("never reads zero samples as stable demand or high agreement", () => {
    renderGauge(score({ evidence: evidence({ status: "unavailable", sample_count: 0, agreement_reportable: false,
      message: "No signal samples in the last 168 hours." }) }));

    expect(screen.getByText(/no signal evidence/i)).toBeInTheDocument();
    expect(screen.getByText("No signal samples in the last 168 hours.")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/Demand looks stable|High \(|\d+%\)/);
  });

  it("says how many samples are missing when evidence is thin", () => {
    renderGauge(score({ sample_count: 2, evidence: evidence({ status: "insufficient", sample_count: 2,
      agreement_reportable: false }) }));
    expect(screen.getByText(/2 samples \(needs 3\)/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/agreement.*\d+%/i);
  });

  it("flags stale signals", () => {
    renderGauge(score({ sample_count: 5, evidence: evidence({ status: "stale", agreement_reportable: false,
      message: "The newest signal sample is from 2026-10-20; signals are stale." }) }));
    expect(screen.getAllByText(/signals are stale/i).length).toBeGreaterThan(0);
  });

  it("reports agreement only with enough fresh evidence", () => {
    renderGauge(score({ score: 0.3, volatility: 0.2, sample_count: 5, evidence: evidence({}) }));
    expect(screen.getByText("High (80%)")).toBeInTheDocument();
  });

  it("shows unavailable, not a neutral score, when the score could not be loaded", () => {
    renderGauge(undefined);
    expect(screen.getByText(/signal score unavailable/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Demand looks stable|\d+%\)/);
  });
});
