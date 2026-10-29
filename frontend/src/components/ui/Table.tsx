import clsx from "clsx";
import { useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp } from "@/components/ui/icons";
import { useMediaQuery } from "@/hooks/useMediaQuery";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
  /** Opt in to client-side sorting. Nulls sort last in both directions. */
  sortValue?: (row: T) => string | number | null | undefined;
  /** Mobile card placement when mobile="cards". */
  priority?: "primary" | "secondary" | "hidden-mobile";
}

interface Selection<T> {
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  label?: (row: T) => string;
}

interface Props<T> {
  data: T[];
  columns: Column<T>[];
  empty?: ReactNode;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  className?: string;
  loading?: boolean;
  loadingRows?: number;
  density?: "comfortable" | "compact";
  maxHeight?: number | string;
  mobile?: "scroll" | "cards";
  selection?: Selection<T>;
  caption?: string;
}

type Sort = { key: string; dir: "asc" | "desc" } | null;

const alignCls = (a?: "left" | "right" | "center") => (a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left");
const isInteractiveTarget = (t: EventTarget) => Boolean((t as HTMLElement).closest("button, a, input, select, textarea, [role='button']"));

function sortRows<T>(data: T[], columns: Column<T>[], sort: Sort): T[] {
  const col = sort && columns.find((c) => c.key === sort.key);
  if (!sort || !col?.sortValue) return data;
  const get = col.sortValue;
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...data].sort((a, b) => {
    const va = get(a), vb = get(b);
    const na = va === null || va === undefined, nb = vb === null || vb === undefined;
    if (na || nb) return na === nb ? 0 : na ? 1 : -1;
    return (typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), undefined, { numeric: true })) * sign;
  });
}

export function Table<T>({ data, columns, empty, rowKey, onRowClick, className, loading, loadingRows = 5, density = "comfortable", maxHeight, mobile = "scroll", selection, caption }: Props<T>) {
  const [sort, setSort] = useState<Sort>(null);
  const rows = useMemo(() => sortRows(data, columns, sort), [data, columns, sort]);
  const small = useMediaQuery("(max-width: 767px)");
  const cellPad = density === "compact" ? "px-3 py-2" : "px-4 py-3";

  if (!loading && data.length === 0) {
    return <div className="rounded-2xl border border-dashed border-line bg-surface-2 py-12 text-center text-sm font-medium text-content-subtle">{empty ?? "No results."}</div>;
  }

  const toggleRow = (key: string) => {
    if (!selection) return;
    const next = new Set(selection.selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    selection.onChange(next);
  };
  const allSelected = selection ? rows.length > 0 && rows.every((r) => selection.selected.has(rowKey(r))) : false;
  const toggleAll = () => selection?.onChange(allSelected ? new Set() : new Set(rows.map(rowKey)));
  const activate = (row: T) => onRowClick?.(row);

  if (small && mobile === "cards" && !loading) {
    const primary = columns.filter((c) => c.priority === "primary");
    const rest = columns.filter((c) => c.priority !== "primary" && c.priority !== "hidden-mobile");
    return (
      <ul aria-label={caption} className={clsx("min-w-0 space-y-2", className)}>
        {rows.map((row) => (
          <li key={rowKey(row)}
            tabIndex={onRowClick ? 0 : undefined}
            onClick={(e) => { if (!isInteractiveTarget(e.target)) activate(row); }}
            onKeyDown={(e) => { if (e.target === e.currentTarget && onRowClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(row); } }}
            className={clsx("focus-ring rounded-xl border border-line bg-surface p-3", onRowClick && "cursor-pointer")}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 font-medium text-content">{primary.map((c) => <div key={c.key}>{c.render(row)}</div>)}</div>
              {selection && <input type="checkbox" aria-label={`Select ${selection.label?.(row) ?? rowKey(row)}`} checked={selection.selected.has(rowKey(row))} onChange={() => toggleRow(rowKey(row))} />}
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {rest.map((c) => (<div key={c.key} className="min-w-0"><dt className="text-content-subtle">{c.header}</dt><dd className="tabular-nums text-content-muted">{c.render(row)}</dd></div>))}
            </dl>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className={clsx("min-w-0 overflow-auto rounded-2xl border border-line bg-surface", className)} style={maxHeight !== undefined ? { maxHeight } : undefined}>
      <table className="t-table w-full border-collapse" aria-busy={loading || undefined}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-10">
          <tr className="bg-surface-2">
            {selection && (
              <th scope="col" className={clsx(cellPad, "w-10 border-b border-line")}>
                <input type="checkbox" aria-label="Select all rows" checked={allSelected} onChange={toggleAll} />
              </th>
            )}
            {columns.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th key={c.key} scope="col" style={c.width ? { width: c.width } : undefined}
                  aria-sort={c.sortValue ? (active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none") : undefined}
                  className={clsx(cellPad, "whitespace-nowrap border-b border-line text-xs font-medium text-content-muted", alignCls(c.align))}>
                  {c.sortValue ? (
                    <button type="button" className={clsx("focus-ring inline-flex items-center gap-1 rounded hover:text-content", c.align === "right" && "flex-row-reverse")}
                      onClick={() => setSort(active && sort!.dir === "asc" ? { key: c.key, dir: "desc" } : { key: c.key, dir: "asc" })}>
                      {c.header}
                      {active ? (sort!.dir === "asc" ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />) : null}
                    </button>
                  ) : c.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: loadingRows }).map((_, i) => (
                <tr key={`skeleton-${i}`} className="border-b border-line last:border-0">
                  {selection && <td className={cellPad} />}
                  {columns.map((c) => <td key={c.key} className={cellPad}><div className="h-3.5 animate-pulse rounded bg-surface-2" /></td>)}
                </tr>
              ))
            : rows.map((row, i) => {
                const key = rowKey(row);
                return (
                  <tr key={key}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={(e) => { if (!isInteractiveTarget(e.target)) activate(row); }}
                    onKeyDown={(e) => { if (e.target === e.currentTarget && onRowClick && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(row); } }}
                    className={clsx("border-b border-line transition-colors duration-fast ease-standard last:border-0", i % 2 === 1 && "bg-surface-2/50", onRowClick && "focus-ring cursor-pointer hover:bg-accent-soft", selection?.selected.has(key) && "bg-accent-soft")}>
                    {selection && (
                      <td className={cellPad}>
                        <input type="checkbox" aria-label={`Select ${selection.label?.(row) ?? key}`} checked={selection.selected.has(key)} onChange={() => toggleRow(key)} />
                      </td>
                    )}
                    {columns.map((c) => <td key={c.key} className={clsx(cellPad, "font-medium text-content-muted tabular-nums", alignCls(c.align))}>{c.render(row)}</td>)}
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}

export const DataTable = Table;
