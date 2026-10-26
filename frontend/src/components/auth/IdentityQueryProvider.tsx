import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { createAppQueryClient } from "@/components/auth/queryClient";
import { useAuthStore } from "@/stores/auth";

/**
 * One query cache per signed-in identity (tenant + user).
 *
 * A single app-wide cache served the previous account's rows to the next one
 * whenever a query key matched — ['decisions', 'fashion', 'open'] is the same
 * key for every fashion workspace — and RLS cannot protect data already in the
 * browser. Isolating by client rather than by key means no current or future
 * query can forget the tenant.
 *
 * On an identity change (sign-in, sign-out, account switch) the previous
 * client's in-flight work is cancelled and its cache cleared, and the subtree
 * remounts so every `useQuery` observer binds to the new client. Keep this
 * inside the router: remounting the router itself would orphan navigations
 * issued during sign-in.
 */
export function IdentityQueryProvider({ children }: { children: ReactNode }) {
  const identityKey = useAuthStore((s) =>
    s.isAuthenticated && s.tenantId && s.userId ? `${s.tenantId}:${s.userId}` : "anon",
  );
  // State, not memo: the client is a resource React must not discard and rebuild.
  const [current, setCurrent] = useState(() => ({ key: identityKey, client: createAppQueryClient() }));
  let active = current;
  if (current.key !== identityKey) {
    active = { key: identityKey, client: createAppQueryClient() };
    setCurrent(active);
  }

  // Retire the previous identity's client once the new one is in place. Only
  // the previous one is touched, so StrictMode's dev double-mount cannot clear
  // the live cache.
  const previous = useRef<QueryClient | null>(null);
  useEffect(() => {
    const old = previous.current;
    if (old && old !== active.client) {
      void old.cancelQueries();
      old.clear();
    }
    previous.current = active.client;
  }, [active.client]);

  return (
    <QueryClientProvider client={active.client}>
      <Fragment key={active.key}>{children}</Fragment>
    </QueryClientProvider>
  );
}
