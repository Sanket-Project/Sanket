import type { ReactNode } from "react";
import { useTenantIndustry } from "@/hooks/useTenantIndustry";
import { useAuthStore } from "@/stores/auth";
import type { IndustryCode } from "@/types/api";

/**
 * Gate a route on the workspace's industry.
 *
 * Presentation only — the server returns 403 for the same request, and that is
 * the boundary that matters. This exists so a manually typed URL produces one
 * clear sentence instead of a screen of failed queries.
 *
 * Renders nothing until the session resolves, so another industry's page can
 * never flash while auth is still loading.
 */
export const IndustryRoute = ({
  industry,
  children,
}: {
  industry: IndustryCode;
  children: ReactNode;
}) => {
  const ready = useAuthStore((s) => s.ready);
  const tenantIndustry = useTenantIndustry();

  if (!ready || tenantIndustry === null) return null;

  if (tenantIndustry !== industry) {
    return (
      <div className="grid place-items-center p-16 text-center">
        <div className="max-w-md space-y-2">
          <h1 className="font-heading text-xl font-semibold text-content">
            Not available for this workspace
          </h1>
          <p className="text-sm text-content-subtle">
            This workspace plans for a different industry, so this module is not
            part of it.
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};
