import { describe, expect, it } from "vitest";
import { INDIA_STATE_DISTRICTS } from "./indiaRegions";

describe("Telangana district reference", () => {
  it("includes all 33 official districts without duplicates, including Hyderabad and the newer districts", () => {
    const districts = INDIA_STATE_DISTRICTS.Telangana;
    expect(districts).toHaveLength(33);
    expect(new Set(districts).size).toBe(33);
    expect(districts).toEqual(expect.arrayContaining([
      "Hyderabad", "Hanumakonda", "Mulugu", "Narayanpet", "Jogulamba Gadwal", "Kumuram Bheem", "Yadadri Bhuvanagiri",
    ]));
  });
});
