import clsx from "clsx";
import { CheckCircle2, Boxes, Receipt, Plug, AlertTriangle, RefreshCw } from "@/components/ui/icons";
import {
  forwardRef,
  useImperativeHandle,
  useState,
  useMemo,
  type ReactNode,
} from "react";
import toast from "react-hot-toast";

import { integrationsApi, type UploadResult } from "@/api/integrations";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { getErrorMessage } from "@/utils/errors";
import { describeUploadResult } from "@/utils/uploadSummary";
import type { StepHandle, StepProps } from "./types";

type Kind = "products" | "sales";

interface ImportCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  kind: Kind;
  onImported: (kind: Kind, result: UploadResult) => void;
}

const ImportCard = ({ icon, title, description, kind, onImported }: ImportCardProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [identity, setIdentity] = useState<"transaction" | "period">("transaction");

  // Analysis states
  const [headers, setHeaders] = useState<string[] | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  const handleFileChange = async (selectedFile: File | null) => {
    setFile(selectedFile);
    setResult(null);
    if (!selectedFile) {
      setHeaders(null);
      setMapping({});
      return;
    }

    setAnalyzing(true);
    try {
      const data = await integrationsApi.analyze(selectedFile, kind);
      setHeaders(data.headers);
      setMapping(data.suggested_mapping || {});
    } catch (err: any) {
      toast.error(getErrorMessage(err, "Failed to analyze file structure"));
      setFile(null);
    } finally {
      setAnalyzing(false);
    }
  };

  const fields = useMemo(() => {
    if (kind === "sales") {
      return [
        { key: "sku", label: "SKU Code", required: false },
        { key: "name", label: "Product Name", required: false },
        { key: "quantity", label: "Quantity", required: true },
        { key: "timestamp", label: "Date / Timestamp", required: true },
        { key: "price", label: "Unit Price", required: false },
      ];
    }
    return [
      { key: "sku", label: "SKU Code", required: false },
      { key: "name", label: "Product Name", required: false },
      { key: "category", label: "Category", required: false },
      { key: "price", label: "Unit Price / Cost", required: false },
    ];
  }, [kind]);

  const validationError = useMemo(() => {
    if (!file || analyzing) return null;
    const mappedKeys = Object.keys(mapping).filter((k) => mapping[k]);
    
    if (kind === "sales") {
      if (!mappedKeys.includes("sku") && !mappedKeys.includes("name")) {
        return "Map either SKU or Product Name";
      }
      if (!mappedKeys.includes("quantity")) return "Map Quantity column";
      if (!mappedKeys.includes("timestamp")) return "Map Date column";
    } else {
      if (!mappedKeys.includes("sku") && !mappedKeys.includes("name")) {
        return "Map either SKU or Product Name";
      }
    }
    return null;
  }, [file, mapping, kind, analyzing]);

  const updateMapping = (key: string, val: string) => {
    setMapping((prev) => ({
      ...prev,
      [key]: val,
    }));
  };

  const run = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const res = await integrationsApi.upload(file, kind, mapping, kind === "sales" ? { identity } : {});
      // A re-uploaded sales file inserts nothing new; that is success, not failure.
      const main =
        kind === "products"
          ? res.skus_created
          : res.rows_inserted + res.rows_updated + res.rows_unchanged;
      if (main === 0) {
        const message =
          res.rows_total === 0
            ? "No rows found — check the file has a header row and at least one data row"
            : res.errors.length
              ? `Import failed: ${res.errors.slice(0, 2).join("; ")}`
              : "No rows could be imported — check the file's columns";
        toast.error(message);
        return;
      }
      setResult(res);
      onImported(kind, res);
      toast.success(describeUploadResult(res));
    } catch {
      /* interceptor surfaces the toast */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-line bg-surface p-5 flex flex-col justify-between">
      <div>
        <div className="mb-3 flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-surface-3 text-content-muted">
            {icon}
          </span>
          <div>
            <h3 className="font-heading text-sm font-semibold tracking-tight text-content">{title}</h3>
            <p className="text-xs text-content-subtle">{description}</p>
          </div>
        </div>

        <FileDropzone file={file} onFile={handleFileChange} hint="CSV or Excel · up to 10 MB" />

        {analyzing && (
          <div className="mt-3 flex items-center gap-2 text-xs text-content-subtle animate-pulse">
            <RefreshCw size={13} className="animate-spin text-[var(--accent)]" />
            <span>Analyzing file layout...</span>
          </div>
        )}

        {file && !analyzing && headers && (
          <div className="mt-3 space-y-3 animate-fade-in">
            {kind === "sales" && (
              <fieldset className="space-y-2 rounded-xl border border-line p-3 text-xs">
                <legend>If this file is uploaded again</legend>
                <label className="flex items-center gap-2">
                  <input type="radio" name="sales-identity" checked={identity === "transaction"}
                    onChange={() => setIdentity("transaction")} />
                  Individual sales (identical rows are skipped)
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="sales-identity" checked={identity === "period"}
                    onChange={() => setIdentity("period")} />
                  Weekly/daily totals (corrections replace)
                </label>
                <p className="text-content-subtle">For totals, use one row per SKU, location, channel and date.</p>
              </fieldset>
            )}
            <div className="rounded-xl border border-line p-3 bg-surface-2/40 space-y-2.5 shadow-sm">
              <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">
                Map File Columns
              </div>
              <div className="grid grid-cols-1 gap-2.5">
                {fields.map((f) => (
                  <div key={f.key} className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium text-content shrink-0">
                      {f.label} {f.required && <span className="text-[9px] text-rose-500 font-bold">*</span>}
                    </span>
                    <select
                      className="input py-1 px-2 text-[11px] h-7 bg-surface border-line max-w-[150px]"
                      value={mapping[f.key] ?? ""}
                      onChange={(e) => updateMapping(f.key, e.target.value)}
                    >
                      <option value="">— Skip —</option>
                      {headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {validationError && (
              <div className="flex items-start gap-2 p-2 rounded-lg bg-amber-50/70 border border-amber-200 text-amber-800 dark:bg-amber-900/10 dark:border-amber-900/30 dark:text-amber-400 text-[10px]">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                <span>{validationError}</span>
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-surface-2 px-3.5 py-2.5 text-xs animate-fade-in">
            <span className="inline-flex items-center gap-1.5 font-medium text-content">
              <CheckCircle2 size={14} className="text-emerald-600" aria-hidden="true" />
              {describeUploadResult(result)}
            </span>
            {kind === "products" ? (
              <span className="font-mono text-content-subtle">
                {result.products_created} products · {result.skus_created} SKUs
              </span>
            ) : (
              <span className="font-mono text-content-subtle">{result.rows_total.toLocaleString()} rows in file</span>
            )}
            {kind === "products" && result.rows_skipped > 0 && (
              <span className="font-mono text-amber-600">{result.rows_skipped} skipped</span>
            )}
          </div>
        )}
      </div>

      <div className="mt-3 pt-2">
        <Button size="sm" variant="secondary" disabled={!file || analyzing || busy || !!validationError} loading={busy} onClick={run}>
          {result ? "Re-import" : "Import"}
        </Button>
      </div>
    </div>
  );
};

export const StepData = forwardRef<StepHandle, StepProps>(function StepData(
  { nextStep, thisStep, save },
  ref,
) {
  const [counts, setCounts] = useState<Record<string, number>>({});

  const onImported = (kind: Kind, res: UploadResult) =>
    setCounts((c) => ({
      ...c,
      [kind]: kind === "products" ? res.skus_created : res.sales_rows,
    }));

  useImperativeHandle(ref, () => ({
    submit: async () => {
      await save({
        mark_step: thisStep,
        current_step: nextStep,
        step_meta: { skus: counts.products ?? 0, sales_rows: counts.sales ?? 0 },
      });
      return true;
    },
  }));

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <ImportCard
          icon={<Boxes size={17} aria-hidden="true" />}
          title="Product catalog"
          description="SKUs, attributes, costs"
          kind="products"
          onImported={onImported}
        />
        <ImportCard
          icon={<Receipt size={17} aria-hidden="true" />}
          title="Sales history"
          description="Historical units sold"
          kind="sales"
          onImported={onImported}
        />
      </div>

      <div
        className={clsx(
          "flex items-start gap-3 rounded-2xl border border-line bg-surface-2 px-4 py-3.5",
        )}
      >
        <Plug size={16} className="mt-0.5 shrink-0 text-content-subtle" aria-hidden="true" />
        <p className="text-xs leading-relaxed text-content-subtle">
          Prefer a live feed? Connect Shopify, Amazon FBA, and 30+ sources anytime from{" "}
          <span className="font-medium text-content-muted">Integrations</span> once you're in. You
          can also skip this step and import later.
        </p>
      </div>
    </div>
  );
});
