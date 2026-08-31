import { beforeEach, describe, expect, it } from "vitest";
import { useIndustryStore } from "@/stores/industry";

/**
 * The industry store used to be writable and localStorage-persisted, which made
 * it a second, client-owned source of truth: the UI could set it, and a stale
 * value could outlive a logout and be sent back to the server as
 * `X-Industry-Code`. A workspace now has exactly one industry, decided by the
 * server, so the store is a read-only projection of the verified session.
 */
describe("industry store", () => {
  beforeEach(() => {
    localStorage.clear();
    useIndustryStore.getState().setSessionIndustry(null);
  });

  it("offers the UI no way to change industry", () => {
    expect("setIndustry" in useIndustryStore.getState()).toBe(false);
  });

  it("starts with no industry until a session supplies one", () => {
    expect(useIndustryStore.getState().activeIndustry).toBeNull();
  });

  it("does not persist the industry to localStorage", () => {
    useIndustryStore.getState().setSessionIndustry("pharma");
    expect(localStorage.getItem("sanket.industry")).toBeNull();
  });

  it("cannot be overridden by stale persisted state from an earlier version", () => {
    localStorage.setItem(
      "sanket.industry",
      JSON.stringify({ state: { activeIndustry: "pharma" }, version: 0 }),
    );
    useIndustryStore.getState().setSessionIndustry("fashion");
    expect(useIndustryStore.getState().activeIndustry).toBe("fashion");
  });

  it("clears on logout so the next account does not inherit it", () => {
    useIndustryStore.getState().setSessionIndustry("pharma");
    useIndustryStore.getState().setSessionIndustry(null);
    expect(useIndustryStore.getState().activeIndustry).toBeNull();
  });
});
