import clsx from "clsx";
import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
}

interface Props<T> {
  data: T[];
  columns: Column<T>[];
  empty?: ReactNode;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  className?: string;
}

export function Table<T>({
  data,
  columns,
  empty,
  rowKey,
  onRowClick,
  className,
}: Props<T>) {
  if (data.length === 0) {
    return (
      <div className="text-center text-content-subtle py-12 text-sm font-medium border border-dashed border-line rounded-2xl bg-surface-2">
        {empty ?? "No results."}
      </div>
    );
  }

  const alignCls = (a?: "left" | "right" | "center") =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div className={clsx("overflow-x-auto rounded-xl border border-line", className)}>
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 z-10">
          <tr className="bg-surface-2">
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={clsx(
                  "px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-content-subtle border-b border-line whitespace-nowrap",
                  alignCls(c.align),
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={rowKey(row)}
              onClick={() => onRowClick?.(row)}
              className={clsx(
                "border-b border-line last:border-0 transition-colors duration-150",
                i % 2 === 1 && "bg-surface-2/50",
                onRowClick && "cursor-pointer hover:bg-[var(--accent-soft)]",
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={clsx(
                    "px-4 py-3 text-content-muted font-medium tabular-figs",
                    alignCls(c.align),
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
