import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, Check, Cpu, Pill, Shirt, Wheat, Wrench } from "@/components/ui/icons";
import type { ReactNode } from "react";
import { industryApi } from "@/api/industry";
import type { IndustryCode } from "@/types/api";

const ICONS: Record<string, ReactNode> = {
  fashion: <Shirt size={16} aria-hidden="true" />,
  electronics: <Cpu size={16} aria-hidden="true" />,
  pharma: <Pill size={16} aria-hidden="true" />,
  agrocenter: <Wheat size={16} aria-hidden="true" />,
  hardware: <Wrench size={16} aria-hidden="true" />,
};

/**
 * Choose the industry a new workspace is scoped to.
 *
 * Options come from the backend's public catalog rather than a list in this
 * file, so the picker cannot drift from the codes the API will accept — the
 * frontend previously kept its own copy in three places.
 *
 * Shared by the email/password sign-up form and the Google workspace modal:
 * both create a workspace, so both must ask, or one of them silently picks for
 * the customer the way signup used to default everyone to Fashion.
 */
export const IndustryPicker = ({
  value,
  onChange,
  disabled,
}: {
  value: IndustryCode | null;
  onChange: (code: IndustryCode) => void;
  disabled?: boolean;
}) => {
  const { data, isLoading } = useQuery({
    queryKey: ["industry", "catalog"],
    queryFn: industryApi.catalog,
    staleTime: 60 * 60_000,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-[60px] animate-pulse rounded-xl bg-surface-3" />
        ))}
      </div>
    );
  }

  return (
    <fieldset disabled={disabled}>
      <legend className="text-sm font-semibold text-content">Choose your industry</legend>
      <p id="industry-picker-help" className="mb-3 mt-1 text-xs leading-5 text-content-subtle">
        This tunes forecast horizons and workflows for everyone in the workspace.
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup" aria-describedby="industry-picker-help">
        {Object.entries(data ?? {}).map(([code, meta]) => {
          const selected = value === code;
          return (
            <button
              key={code}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={meta.display_name}
              onClick={() => onChange(code as IndustryCode)}
              className={clsx(
                "min-h-[60px] cursor-pointer items-center gap-2.5 rounded-xl border p-3 text-left outline-none transition-all duration-150 focus-visible:ring-2 focus-visible:ring-[var(--accent-ring)] disabled:cursor-not-allowed disabled:opacity-60 flex",
                selected
                  ? "border-accent bg-accent-soft shadow-sm"
                  : "border-line bg-surface hover:border-line-strong hover:bg-surface-2",
              )}
            >
              <span
                className={clsx(
                  "grid h-8 w-8 shrink-0 place-items-center rounded-lg",
                  selected ? "bg-accent text-accent-fg" : "bg-surface-3 text-content-muted",
                )}
              >
                {ICONS[code] ?? <Building2 size={16} aria-hidden="true" />}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold leading-5 text-content">
                  {meta.display_name}
                </span>
                <span className="block font-mono text-[10px] text-content-subtle">
                  {meta.default_horizon_weeks}-wk horizon
                </span>
              </span>
              <span
                aria-hidden="true"
                className={clsx(
                  "ml-auto grid h-5 w-5 shrink-0 place-items-center rounded-full border transition-colors",
                  selected ? "border-accent bg-accent text-accent-fg" : "border-line-strong bg-surface",
                )}
              >
                {selected && <Check size={12} />}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
};
