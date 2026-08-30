import { describe, expect, it } from "vitest";
import { getProductImage } from "./productImages";

const cases = [
  ["electronics", "EL-HEADPHONE-01", "electronics-headphones.webp"],
  ["electronics", "EL-SPEAKER-01", "electronics-speaker.webp"],
  ["electronics", "EL-LAPTOP-01", "electronics-laptop.webp"],
  ["electronics", "EL-SMARTWATCH-01", "electronics-smartwatch.webp"],
  ["pharma", "PH-IBU-01", "pharma-ibuprofen.webp"],
  ["pharma", "PH-AMOX-01", "pharma-amoxicillin.webp"],
  ["pharma", "PH-INSULIN-01", "pharma-insulin-pen.webp"],
  ["pharma", "PH-VITC-01", "pharma-vitamin-c.webp"],
  ["agrocenter", "AG-FEED-01", "agro-poultry-feed.webp"],
  ["agrocenter", "AG-FERT-01", "agro-fertilizer.webp"],
  ["agrocenter", "AG-PEST-01", "agro-pesticide.webp"],
  ["agrocenter", "AG-SEED-01", "agro-corn-seed.webp"],
  ["hardware", "HW-CEMENT-01", "hardware-cement.webp"],
  ["hardware", "HW-WIRE-01", "hardware-wire.webp"],
  ["hardware", "HW-FAST-01", "hardware-fasteners.webp"],
  ["hardware", "HW-PIPE-01", "hardware-pvc-pipe.webp"],
  ["hardware", "HW-DRILL-01", "hardware-drill.webp"],
  ["hardware", "HW-PPE-01", "hardware-safety-helmet.webp"],
] as const;

describe("getProductImage", () => {
  it.each(cases)("maps %s SKU %s to %s", (industry, sku, expected) => {
    expect(getProductImage("id", industry, {}, sku)).toMatch(new RegExp(`${expected}$`));
  });

  it("keeps user-uploaded images as the highest-priority source", () => {
    expect(getProductImage("custom", "hardware", { custom: "data:image/png;base64,abc" }, "HW-DRILL-01"))
      .toBe("data:image/png;base64,abc");
  });
});
