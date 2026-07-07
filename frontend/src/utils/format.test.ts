import { describe, expect, it } from "vitest";
import {
  fmtCompact,
  fmtCurrency,
  fmtDate,
  fmtNumber,
  fmtPct,
} from "./format";

describe("format utils", () => {
  describe("null/undefined handling", () => {
    it("renders an em-dash for nullish values", () => {
      expect(fmtNumber(null)).toBe("—");
      expect(fmtNumber(undefined)).toBe("—");
      expect(fmtCurrency(null)).toBe("—");
      expect(fmtCompact(null)).toBe("—");
      expect(fmtPct(null)).toBe("—");
      expect(fmtDate(null)).toBe("—");
      expect(fmtDate("")).toBe("—");
    });
  });

  describe("fmtNumber", () => {
    it("adds thousands separators", () => {
      expect(fmtNumber(1000)).toBe("1,000");
      expect(fmtNumber(1234567)).toBe("1,234,567");
    });
    it("respects the digits argument", () => {
      expect(fmtNumber(3.14159, 2)).toBe("3.14");
    });
    it("formats zero (not treated as nullish)", () => {
      expect(fmtNumber(0)).toBe("0");
    });
  });

  describe("fmtCurrency", () => {
    it("formats USD with no fraction digits", () => {
      expect(fmtCurrency(1000)).toBe("$1,000");
      expect(fmtCurrency(0)).toBe("$0");
    });
  });

  describe("fmtCompact", () => {
    it("uses compact notation", () => {
      expect(fmtCompact(1500)).toBe("1.5K");
      expect(fmtCompact(2_000_000)).toBe("2M");
    });
  });

  describe("fmtPct", () => {
    it("multiplies by 100 and appends a percent sign", () => {
      expect(fmtPct(0.5)).toBe("50.0%");
      expect(fmtPct(0.1234, 2)).toBe("12.34%");
    });
  });

  describe("fmtDate", () => {
    it("formats a valid ISO date", () => {
      expect(fmtDate("2024-01-15")).toBe("Jan 15, 2024");
    });
    it("returns em-dash for an invalid date string", () => {
      expect(fmtDate("not-a-date")).toBe("—");
    });
  });
});
