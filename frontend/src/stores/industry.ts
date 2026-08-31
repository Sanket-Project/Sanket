import { create } from "zustand";
import type { IndustryCode } from "@/types/api";

/**
 * The workspace's industry, projected from the verified session.
 *
 * This used to be writable and localStorage-persisted, which made it a second,
 * client-owned source of truth. Two things went wrong with that. The UI could
 * change it — that was the whole point of the industry switcher — and a value
 * written by one account survived logout, so the next session could start on
 * the previous workspace's industry and send it back to the server as
 * `X-Industry-Code`.
 *
 * A workspace now has exactly one industry and the server decides it, so the
 * only writer here is `auth.setSession`. Components should read
 * `useTenantIndustry()` rather than reaching for this store directly.
 */
interface IndustryState {
  /** Null until a verified session supplies one, and again after logout. */
  activeIndustry: IndustryCode | null;
  /** Internal — called by the auth store when a session is established or cleared. */
  setSessionIndustry: (industry: IndustryCode | null) => void;
}

export const useIndustryStore = create<IndustryState>()((set) => ({
  activeIndustry: null,
  setSessionIndustry: (industry) => set({ activeIndustry: industry }),
}));

// Drop the key earlier versions persisted. Without this, a browser that used
// the old build keeps a stale industry in localStorage indefinitely — harmless
// now that nothing reads it, but it is the kind of leftover that quietly
// becomes load-bearing again.
try {
  localStorage.removeItem("sanket.industry");
} catch {
  /* storage may be unavailable (private mode, blocked site data) */
}
