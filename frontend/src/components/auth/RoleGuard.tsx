import type { ReactNode } from "react";
import { useAuthStore } from "@/stores/auth";
import type { UserRole } from "@/types/api";

interface RoleGuardProps {
  roles: UserRole[];
  children: ReactNode;
  fallback?: ReactNode;
}

/** Renders children only if the authenticated user has one of the specified roles. */
export const RoleGuard = ({ roles, children, fallback = null }: RoleGuardProps) => {
  const role = useAuthStore((s) => s.role);
  if (!role || !roles.includes(role)) return <>{fallback}</>;
  return <>{children}</>;
};
