import { useAuthStore } from "@/stores/auth";
import type { IndustryCode } from "@/types/api";

/**
 * The authenticated workspace's industry.
 *
 * Derived from the verified session rather than from local state, so a value
 * cannot outlive a logout or leak into another account's session. Null while
 * the session is still resolving and after sign-out — callers inside
 * `ProtectedRoute` can treat null as "not ready yet" and render nothing, which
 * is also what stops another industry's UI flashing during bootstrap.
 */
export const useTenantIndustry = (): IndustryCode | null =>
  useAuthStore((s) => s.industry);
