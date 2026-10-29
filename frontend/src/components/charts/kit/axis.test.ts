import { expect, it } from "vitest";
import { formatCompact, formatDateTick } from "./axis";

it("formats date ticks by granularity in UTC", () => {
  expect(formatDateTick("2026-08-03", "day")).toBe("3 Aug");
  expect(formatDateTick("2026-08-03", "week")).toBe("3 Aug");
  expect(formatDateTick("2026-08-01", "month")).toBe("Aug 2026");
});

it("compacts large numbers without inventing precision", () => {
  expect(formatCompact(950)).toBe("950");
  expect(formatCompact(1200)).toBe("1.2k");
  expect(formatCompact(3_400_000)).toBe("3.4M");
  expect(formatCompact(0)).toBe("0");
});
