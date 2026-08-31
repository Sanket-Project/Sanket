import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, Cpu, Pill, Shirt, Wheat, Wrench } from "@/components/ui/icons";
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
          <div key={i} className="h-[52px] animate-pulse rounded-xl bg-surface-3" />
        ))}
      </div>
    );
  }

  return (
    <fieldset disabled={disabled}>
      <legend className="mb-2 text-sm font-medium text-content">
        Industry
        <span className="ml-1.5 text-xs font-normal text-content-subtle">
          Everyone you invite plans in this industry. It locks once setup is done.
        </span>
      </legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup">
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
                "flex items-center gap-2.5 rounded-xl border p-3 text-left transition-colors",
                selected
                  ? "border-accent bg-accent-soft"
                  : "border-line bg-surface hover:border-line-strong",
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
                <span className="block truncate text-sm font-medium text-content">
                  {meta.display_name}
                </span>
                <span className="block font-mono text-[10px] text-content-subtle">
                  {meta.default_horizon_weeks}-wk horizon
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
};
