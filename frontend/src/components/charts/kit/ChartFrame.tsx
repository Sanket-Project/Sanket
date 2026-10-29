// src/components/charts/kit/ChartFrame.tsx
import { useId, type ReactNode } from "react";
import { ErrorState, LoadingState, UnavailableState } from "@/components/ui/StateViews";

interface Props {
  title: ReactNode; description?: ReactNode; controls?: ReactNode; legend?: ReactNode; height?: number;
  state?: "ready" | "loading" | "empty" | "error"; emptyTitle?: string; emptyReason?: ReactNode; onRetry?: () => void; children: ReactNode;
}

/** Fixed-height plot area so state changes never shift the layout. */
export const ChartFrame = ({ title, description, controls, legend, height = 300, state = "ready", emptyTitle = "Nothing to chart yet", emptyReason = "There is no recorded data for this view.", onRetry, children }: Props) => {
  const titleId = useId();
  return (
    <figure aria-labelledby={titleId} className="min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={titleId} className="t-card">{title}</h3>
          {description && <p className="mt-1 text-xs text-content-subtle">{description}</p>}
        </div>
        {controls && <div className="flex flex-wrap items-center gap-2">{controls}</div>}
      </div>
      <div style={{ height }} className="grid min-w-0">
        {state === "loading" ? <LoadingState variant="chart" label="Loading chart" />
          : state === "error" ? <div className="self-center"><ErrorState onRetry={onRetry} /></div>
          : state === "empty" ? <div className="self-center"><UnavailableState title={emptyTitle} reason={emptyReason} /></div>
          : children}
      </div>
      {legend && state === "ready" && <figcaption className="mt-3">{legend}</figcaption>}
    </figure>
  );
};
