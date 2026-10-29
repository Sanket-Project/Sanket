// src/hooks/useMediaQuery.ts
import { useEffect, useState } from "react";

const query$ = (q: string) => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(q) : null);

/** False when matchMedia is unavailable (tests, SSR), so callers default to the desktop layout. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => query$(query)?.matches ?? false);
  useEffect(() => {
    const mql = query$(query);
    if (!mql) return;
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, [query]);
  return matches;
}
