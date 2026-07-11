import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { IndustryCode } from "@/types/api";

/** The industry a fresh session starts from. Single source of truth so callers
 *  that need to reset (e.g. logout) don't hardcode the value and drift. */
export const DEFAULT_INDUSTRY: IndustryCode = "fashion";

interface IndustryState {
  activeIndustry: IndustryCode;
  setIndustry: (i: IndustryCode) => void;
  reset: () => void;
}

export const useIndustryStore = create<IndustryState>()(
  persist(
    (set) => ({
      activeIndustry: DEFAULT_INDUSTRY,
      setIndustry: (i) => set({ activeIndustry: i }),
      reset: () => set({ activeIndustry: DEFAULT_INDUSTRY }),
    }),
    {
      name: "sanket.industry",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
