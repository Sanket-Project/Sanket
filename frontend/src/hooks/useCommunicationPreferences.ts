import { useQuery } from "@tanstack/react-query";
import { communicationsApi } from "@/api/communications";
import { useAuthStore } from "@/stores/auth";

export function useCommunicationPreferences() {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const authenticated = useAuthStore((s) => Boolean(s.tenantId && s.userId));
  return useQuery({ queryKey: ["communication-preferences", scope], queryFn: communicationsApi.preferences, enabled: authenticated });
}
