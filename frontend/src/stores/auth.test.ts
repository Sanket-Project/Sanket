import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "@/stores/auth";
import type { SessionInfo } from "@/types/api";

/**
 * The workspace industry lives on the session and nowhere else.
 *
 * It used to live in its own writable, localStorage-persisted store, which made
 * it a second client-owned source of truth: the UI could change it, and a value
 * written by one account survived logout into the next.
 */
const session = (industry: "fashion" | "pharma"): SessionInfo => ({
  user_id: "u",
  tenant_id: "t",
  role: "owner",
  active_industry: industry,
  email: "owner@example.com",
  full_name: "Owner",
});

describe("auth store industry", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ industry: null, isAuthenticated: false });
  });

  it("takes the industry from the verified session", () => {
    useAuthStore.getState().setSession(session("pharma"), "tok");
    expect(useAuthStore.getState().industry).toBe("pharma");
  });

  it("never persists the industry on its own", () => {
    useAuthStore.getState().setSession(session("pharma"), "tok");
    expect(localStorage.getItem("sanket.industry")).toBeNull();
  });

  it("sets the industry in the same update that authenticates", () => {
    // If these could be observed apart, a component would render authenticated
    // with no industry — the frame in which another industry's UI used to flash.
    let sawAuthenticatedWithoutIndustry = false;
    const unsubscribe = useAuthStore.subscribe((s) => {
      if (s.isAuthenticated && !s.industry) sawAuthenticatedWithoutIndustry = true;
    });
    useAuthStore.getState().setSession(session("fashion"), "tok");
    unsubscribe();
    expect(sawAuthenticatedWithoutIndustry).toBe(false);
  });

  it("exposes no setter the UI could use to change industry", () => {
    expect("setIndustry" in useAuthStore.getState()).toBe(false);
    expect("setSessionIndustry" in useAuthStore.getState()).toBe(false);
  });
});
