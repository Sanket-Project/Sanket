import clsx from "clsx";
import { FileSpreadsheet, UploadCloud, X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";

interface Props {
  onFile: (file: File | null) => void;
  file?: File | null;
  /** accept attribute, e.g. ".csv,.xlsx" */
  accept?: string;
  label?: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
}

/**
 * Drag-and-drop / click file picker for catalog & sales-history import. Token
 * driven, keyboard-accessible. Validates nothing about contents — that's the
 * server's job; this only captures the chosen File.
 */
export const FileDropzone = ({
  onFile,
  file,
  accept = ".csv,.xlsx,.xls",
  label = "Drop a file or click to browse",
  hint,
  disabled,
  className,
}: Props) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const id = useId();

  const pick = (f: File | null) => !disabled && onFile(f);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0] ?? null;
    if (f) pick(f);
  };

  if (file) {
    return (
      <div
        className={clsx(
          "flex items-center gap-3 rounded-xl border border-line-strong bg-surface-2 px-4 py-3",
          className,
        )}
      >
        <FileSpreadsheet size={18} className="shrink-0 text-accent" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-content">{file.name}</div>
          <div className="font-mono text-xs text-content-subtle">
            {(file.size / 1024).toFixed(1)} KB
          </div>
        </div>
        <button
          type="button"
          onClick={() => pick(null)}
          disabled={disabled}
          aria-label="Remove file"
          className="rounded-lg p-1.5 text-content-subtle tactile-press hover:bg-surface-3 hover:text-content"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <div className={className}>
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={clsx(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-6 py-9 text-center transition-colors duration-150",
          dragging
            ? "border-accent bg-accent-soft"
            : "border-line-strong bg-surface-2 hover:border-content-subtle",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <UploadCloud
          size={22}
          className={clsx(dragging ? "text-accent" : "text-content-subtle")}
          aria-hidden="true"
        />
        <span className="text-sm font-medium text-content">{label}</span>
        {hint && <span className="text-xs text-content-subtle">{hint}</span>}
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept={accept}
          disabled={disabled}
          className="sr-only"
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
      </label>
    </div>
  );
};
