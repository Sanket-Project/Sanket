import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, Shirt, Cpu, Pill, Wheat, Wrench, Building2 } from "lucide-react";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
  type ReactNode,
} from "react";
import toast from "react-hot-toast";

import { industryApi } from "@/api/industry";
import { useIndustryStore } from "@/stores/industry";
import type { IndustryCode } from "@/types/api";
import type { StepHandle, StepProps } from "./types";

const ICONS: Record<string, ReactNode> = {
  fashion: <Shirt size={18} aria-hidden="true" />,
  electronics: <Cpu size={18} aria-hidden="true" />,
  pharma: <Pill size={18} aria-hidden="true" />,
  agrocenter: <Wheat size={18} aria-hidden="true" />,
  hardware: <Wrench size={18} aria-hidden="true" />,
};

export const StepIndustry = forwardRef<StepHandle, StepProps>(function StepIndustry(
  { nextStep, thisStep, save, onValidityChange },
  ref,
) {
  const setIndustry = useIndustryStore((s) => s.setIndustry);
  const activeIndustry = useIndustryStore((s) => s.activeIndustry);
  const [selected, setSelected] = useState<IndustryCode | null>(activeIndustry ?? null);

  const { data, isLoading } = useQuery({
    queryKey: ["industry", "available"],
    queryFn: industryApi.available,
  });

  useEffect(() => {
    onValidityChange?.(!!selected);
  }, [selected, onValidityChange]);

  useImperativeHandle(ref, () => ({
    submit: async () => {
      if (!selected) {
        toast.error("Choose an industry to continue");
        return false;
      }
      try {
        await industryApi.activate(selected);
        setIndustry(selected);
        await save({
          mark_step: thisStep,
          current_step: nextStep,
          step_meta: { industry: selected },
        });
        return true;
      } catch {
        return false; // client interceptor surfaces the error toast
      }
    },
  }));

  if (isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-[88px] animate-pulse rounded-2xl bg-surface-3" />
        ))}
      </div>
    );
  }

  const entries = Object.entries(data ?? {});

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {entries.map(([code, meta]) => {
        const isSel = selected === code;
        return (
          <button
            key={code}
            type="button"
            onClick={() => setSelected(code as IndustryCode)}
            aria-pressed={isSel}
            className={clsx(
              "group relative flex items-start gap-3.5 rounded-2xl border p-4 text-left tactile-press",
              isSel
                ? "border-accent bg-accent-soft shadow-sm"
                : "border-line bg-surface hover:border-line-strong hover:shadow-sm",
            )}
          >
            <span
              className={clsx(
                "grid h-10 w-10 shrink-0 place-items-center rounded-xl",
                isSel ? "bg-accent text-accent-fg" : "bg-surface-3 text-content-muted",
              )}
            >
              {ICONS[code] ?? <Building2 size={18} aria-hidden="true" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-heading text-sm font-semibold tracking-tight text-content">
                  {meta.display_name}
                </span>
                {isSel && <Check size={15} className="text-accent" aria-hidden="true" />}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-content-subtle">
                <span>{meta.default_horizon_weeks}-wk horizon</span>
                <span className="capitalize">{meta.audit_level} audit</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
});
