import clsx from "clsx";
import { Check } from "lucide-react";
import type { ReactNode } from "react";

export interface StepperItem {
  key: string;
  label: string;
  description?: string;
  icon?: ReactNode;
}

interface Props {
  steps: StepperItem[];
  /** key of the active step */
  current: string;
  /** keys that are complete */
  completed: ReadonlySet<string> | string[];
  /** invoked when a reachable step is clicked (complete steps + the current one) */
  onStepClick?: (key: string) => void;
  className?: string;
}

/**
 * Vertical, workflow-first stepper. Hierarchy comes from weight and the single
 * accent on the active node — no rails of color. Complete steps are navigable;
 * future steps are locked until reached.
 */
export const Stepper = ({ steps, current, completed, onStepClick, className }: Props) => {
  const done = Array.isArray(completed) ? new Set(completed) : completed;

  return (
    <ol className={clsx("flex flex-col", className)} aria-label="Setup progress">
      {steps.map((step, i) => {
        const isDone = done.has(step.key);
        const isCurrent = step.key === current;
        const reachable = isDone || isCurrent;
        const isLast = i === steps.length - 1;

        return (
          <li key={step.key} className="relative flex gap-3.5 pb-1">
            {/* connector */}
            {!isLast && (
              <span
                aria-hidden="true"
                className={clsx(
                  "absolute left-[15px] top-8 bottom-0 w-px",
                  isDone ? "bg-accent/40" : "bg-line-strong",
                )}
              />
            )}

            <button
              type="button"
              disabled={!reachable || !onStepClick}
              onClick={() => reachable && onStepClick?.(step.key)}
              className={clsx(
                "relative z-10 mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full border text-xs font-semibold tactile-press",
                isDone && "border-accent bg-accent text-accent-fg",
                isCurrent && "border-accent bg-accent-soft text-accent",
                !isDone && !isCurrent && "border-line-strong bg-surface text-content-subtle",
                reachable && onStepClick ? "cursor-pointer" : "cursor-default",
              )}
              aria-current={isCurrent ? "step" : undefined}
            >
              {isDone ? <Check size={15} aria-hidden="true" /> : step.icon ?? i + 1}
            </button>

            <div className={clsx("pb-7 pt-1", isLast && "pb-0")}>
              <div
                className={clsx(
                  "text-sm font-semibold leading-none tracking-tight",
                  isCurrent ? "text-content" : isDone ? "text-content-muted" : "text-content-subtle",
                )}
              >
                {step.label}
              </div>
              {step.description && (
                <div className="mt-1.5 text-xs leading-relaxed text-content-subtle">
                  {step.description}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
};
