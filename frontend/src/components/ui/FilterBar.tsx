import type { ReactNode } from "react";
import { X } from "@/components/ui/icons";

export const FilterBar = ({ label, filters, actions, activeCount = 0, onClear }: {
  label: string; filters: ReactNode; actions?: ReactNode; activeCount?: number; onClear?: () => void;
}) => (
  <div role="toolbar" aria-label={label} className="flex min-w-0 flex-wrap items-end justify-between gap-3">
    <div className="flex min-w-0 max-w-full flex-1 flex-nowrap items-end gap-2 overflow-x-auto -m-1 p-1 [&>*]:shrink-0 sm:flex-wrap sm:overflow-visible sm:[&>*]:shrink">
      {filters}
      {activeCount > 0 && onClear && (
        <button type="button" onClick={onClear} className="focus-ring inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-content-muted transition-colors duration-fast ease-standard hover:text-content">
          <X size={14} aria-hidden="true" />Clear filters ({activeCount})
        </button>
      )}
    </div>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </div>
);
