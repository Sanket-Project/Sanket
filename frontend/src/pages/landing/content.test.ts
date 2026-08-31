import { describe, expect, it } from "vitest";
import {
  CONNECTORS,
  INDUSTRY_DETAIL,
  LIVE_CONNECTOR_COUNT,
  MODULES,
  SIGNALS,
  TOTAL_CONNECTOR_COUNT,
} from "@/pages/landing/content";

describe("landing content", () => {
  it("states each industry's real planning horizon and audit level", () => {
    // Mirrors backend/app/services/industry_context.py. Pharma is the one that
    // matters commercially: 52 weeks at GxP audit level.
    expect(INDUSTRY_DETAIL.fashion.horizonWeeks).toBe(26);
    expect(INDUSTRY_DETAIL.electronics.horizonWeeks).toBe(12);
    expect(INDUSTRY_DETAIL.pharma.horizonWeeks).toBe(52);
    expect(INDUSTRY_DETAIL.pharma.auditLevel).toBe("gxp");
    expect(INDUSTRY_DETAIL.agrocenter.horizonWeeks).toBe(26);
    expect(INDUSTRY_DETAIL.hardware.horizonWeeks).toBe(16);
  });

  it("covers all five industries", () => {
    expect(Object.keys(INDUSTRY_DETAIL).sort()).toEqual([
      "agrocenter",
      "electronics",
      "fashion",
      "hardware",
      "pharma",
    ]);
  });

  it("counts connectors honestly", () => {
    // The page used to advertise "29+ CONNECTORS" by counting planned ones.
    expect(TOTAL_CONNECTOR_COUNT).toBe(CONNECTORS.length);
    expect(LIVE_CONNECTOR_COUNT).toBe(
      CONNECTORS.filter((c) => c.availability === "live").length,
    );
    expect(LIVE_CONNECTOR_COUNT).toBeLessThan(TOTAL_CONNECTOR_COUNT);
  });

  it("marks the six working connectors live and nothing else", () => {
    const live = CONNECTORS.filter((c) => c.availability === "live")
      .map((c) => c.name)
      .sort();
    expect(live).toEqual([
      "CSV Upload",
      "Excel Upload",
      "MySQL",
      "PostgreSQL",
      "Shopify",
      "WooCommerce",
    ]);
  });

  it("points every module at a route that exists in the app", () => {
    for (const m of MODULES) {
      expect(m.route, `${m.name} route`).toMatch(/^\/workspace/);
    }
  });

  it("names a source for every signal", () => {
    expect(SIGNALS.length).toBeGreaterThan(3);
    for (const s of SIGNALS) expect(s.source.length).toBeGreaterThan(0);
  });
});
