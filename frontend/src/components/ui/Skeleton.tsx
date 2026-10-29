import clsx from "clsx";

interface SkeletonProps {
  className?: string;
  rows?: number;
}

export const Skeleton = ({ className, rows = 1 }: SkeletonProps) => (
  <div className={clsx("space-y-3", className)}>
    {Array.from({ length: rows }).map((_, i) => (
      <div
        key={i}
        className="animate-pulse rounded-lg bg-surface-2"
        style={{ height: 20, opacity: 1 - i * 0.15 }}
      />
    ))}
  </div>
);

export const SkeletonCard = () => (
  <div className="rounded-2xl border border-line p-5 space-y-3 animate-pulse">
    <div className="h-4 w-1/3 rounded bg-surface-2" />
    <div className="h-3 w-2/3 rounded bg-surface-2" />
    <div className="h-20 rounded-lg bg-surface-2" />
  </div>
);

export const SkeletonRow = () => (
  <div className="flex items-center gap-3 py-2 animate-pulse">
    <div className="h-8 w-8 rounded-lg bg-surface-2 shrink-0" />
    <div className="flex-1 space-y-1.5">
      <div className="h-3.5 w-1/2 rounded bg-surface-2" />
      <div className="h-3 w-1/3 rounded bg-surface-2" />
    </div>
    <div className="h-6 w-16 rounded-full bg-surface-2" />
  </div>
);

export const SkeletonChart = ({ height = 280 }: { height?: number }) => (
  <div className="animate-pulse rounded-xl bg-surface-2" style={{ height }} />
);

export const SkeletonTable = ({ rows = 6, columns = 4 }: { rows?: number; columns?: number }) => (
  <div className="animate-pulse space-y-2">
    {Array.from({ length: rows }).map((_, r) => (
      <div key={r} className="grid gap-3" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {Array.from({ length: columns }).map((__, c) => <div key={c} className="h-4 rounded bg-surface-2" />)}
      </div>
    ))}
  </div>
);
