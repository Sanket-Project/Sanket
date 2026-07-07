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
        className="animate-pulse rounded-lg bg-slate-100"
        style={{ height: 20, opacity: 1 - i * 0.15 }}
      />
    ))}
  </div>
);

export const SkeletonCard = () => (
  <div className="rounded-2xl border border-slate-100 p-5 space-y-3 animate-pulse">
    <div className="h-4 w-1/3 rounded bg-slate-100" />
    <div className="h-3 w-2/3 rounded bg-slate-100" />
    <div className="h-20 rounded-lg bg-slate-100" />
  </div>
);

export const SkeletonRow = () => (
  <div className="flex items-center gap-3 py-2 animate-pulse">
    <div className="h-8 w-8 rounded-lg bg-slate-100 shrink-0" />
    <div className="flex-1 space-y-1.5">
      <div className="h-3.5 w-1/2 rounded bg-slate-100" />
      <div className="h-3 w-1/3 rounded bg-slate-100" />
    </div>
    <div className="h-6 w-16 rounded-full bg-slate-100" />
  </div>
);
