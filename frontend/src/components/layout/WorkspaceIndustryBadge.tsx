import { Cpu, Pill, Shirt, Sprout, Wrench, type AppIcon } from "@/components/ui/icons";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import type { IndustryCode } from "@/types/api";

const INDUSTRY: Record<IndustryCode, { label: string; Icon: AppIcon }> = {
  fashion: { label: "Fashion & Apparel", Icon: Shirt },
  electronics: { label: "Consumer Electronics", Icon: Cpu },
  pharma: { label: "Pharmaceuticals", Icon: Pill },
  agrocenter: { label: "Agrocenter", Icon: Sprout },
  hardware: { label: "Tools & Hardware", Icon: Wrench },
};

/**
 * Names the workspace's industry in the header.
 *
 * Replaces the industry switcher. A workspace is scoped to one industry, so
 * there is nothing to switch to -- and the dropdown listed all five by name,
 * which is exactly what an authenticated user must not see. This is the same
 * information without the affordance: it tells you where you are, and offers no
 * way to be somewhere else.
 */
export const WorkspaceIndustryBadge = () => {
  const industry = useWorkspaceIndustry();
  const { label, Icon } = INDUSTRY[industry];

  return (
    <div className="inline-flex min-w-0 items-center gap-2 sm:gap-3 select-none">
      <span
        className="hidden sm:grid place-items-center h-9 w-9 rounded-xl bg-accent-soft text-accent shrink-0"
      >
        <Icon size={14} aria-hidden="true" />
      </span>
      <div className="min-w-0 leading-none">
        <p className="text-[9px] font-bold uppercase tracking-widest text-content-subtle">
          Workspace
        </p>
        <h4 className="max-w-[150px] truncate font-sans text-xs font-semibold text-content mt-1.5">
          {label}
        </h4>
      </div>
    </div>
  );
};
