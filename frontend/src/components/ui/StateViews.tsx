import type { ReactNode } from "react";
import { AlertTriangle, CircleDashed, RefreshCw } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";
import { Skeleton, SkeletonCard, SkeletonChart, SkeletonTable } from "@/components/ui/Skeleton";
import { getErrorMessage } from "@/utils/errors";

export const LoadingState = ({ variant = "lines", rows = 3, label = "Loading" }: {
  variant?: "lines" | "card" | "chart" | "table"; rows?: number; label?: string;
}) => (
  <div role="status" aria-live="polite" aria-busy="true">
    <span className="sr-only">{label}</span>
    {variant === "card" ? <SkeletonCard /> : variant === "chart" ? <SkeletonChart /> : variant === "table" ? <SkeletonTable rows={rows} /> : <Skeleton rows={rows} />}
  </div>
);

export const ErrorState = ({ title = "Couldn't load this", message, onRetry }: {
  title?: string; message?: ReactNode; onRetry?: () => void;
}) => (
  <div role="alert" className="flex flex-col items-center px-4 py-8 text-center">
    <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400"><AlertTriangle size={18} aria-hidden="true" /></div>
    <p className="t-card">{title}</p>
    {message && <p className="t-body mt-1 max-w-sm">{message}</p>}
    {onRetry && <Button variant="secondary" size="sm" className="mt-4" icon={<RefreshCw size={14} aria-hidden="true" />} onClick={onRetry}>Try again</Button>}
  </div>
);

export const UnavailableState = ({ title, reason, action }: { title: string; reason: ReactNode; action?: ReactNode }) => (
  <div className="flex flex-col items-center px-4 py-8 text-center">
    <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-surface-3 text-content-subtle"><CircleDashed size={18} aria-hidden="true" /></div>
    <p className="t-card">{title}</p>
    <p className="t-body mt-1 max-w-sm">{reason}</p>
    {action && <div className="mt-4">{action}</div>}
  </div>
);

interface QueryLike<T> { data: T | undefined; isLoading: boolean; isError: boolean; error?: unknown; refetch?: () => unknown }

export function QueryBoundary<T>({ query, loading, isEmpty, empty, errorTitle, children }: {
  query: QueryLike<T>; loading?: ReactNode; isEmpty?: (data: T) => boolean; empty?: ReactNode; errorTitle?: string; children: (data: T) => ReactNode;
}) {
  if (query.isLoading) return <>{loading ?? <LoadingState />}</>;
  if (query.isError || query.data === undefined) {
    return <ErrorState title={errorTitle} message={query.error ? getErrorMessage(query.error, "The server did not respond.") : undefined} onRetry={query.refetch ? () => void query.refetch?.() : undefined} />;
  }
  if (isEmpty?.(query.data)) return <>{empty ?? null}</>;
  return <>{children(query.data)}</>;
}
