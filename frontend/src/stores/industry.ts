import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { IndustryCode } from "@/types/api";

interface IndustryState {
  activeIndustry: IndustryCode;
  setIndustry: (i: IndustryCode) => void;
}

export const useIndustryStore = create<IndustryState>()(
  persist(
    (set) => ({
      activeIndustry: "fashion",
      setIndustry: (i) => set({ activeIndustry: i }),
    }),
    {
      name: "sanket.industry",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
