import { Cpu, Pill, Shirt, Sprout, Wrench, type AppIcon } from "@/components/ui/icons";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import type { IndustryCode } from "@/types/api";
import { INDUSTRY_THEME } from "@/utils/colors";

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
    <div className="inline-flex items-center gap-3 pl-2.5 pr-4 py-2 rounded-xl border border-line bg-surface select-none">
      <span
        className="grid place-items-center h-8 w-8 rounded-lg text-white shrink-0 shadow-sm"
        style={{ background: INDUSTRY_THEME[industry].gradient }}
      >
        <Icon size={14} aria-hidden="true" />
      </span>
      <div className="min-w-[110px] leading-none">
        <p className="text-[9px] font-bold uppercase tracking-widest text-content-subtle">
          Workspace
        </p>
        <h4 className="font-heading text-xs font-semibold text-content mt-1.5 tracking-tight">
          {label}
        </h4>
      </div>
    </div>
  );
};
