import clsx from "clsx";
import { CheckCircle2, Boxes, Receipt, Plug } from "lucide-react";
import {
  forwardRef,
  useImperativeHandle,
  useState,
  type ReactNode,
} from "react";
import toast from "react-hot-toast";

import { integrationsApi, type UploadResult } from "@/api/integrations";
import { Button } from "@/components/ui/Button";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { useIndustryStore } from "@/stores/industry";
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
  const industry = useIndustryStore((s) => s.activeIndustry);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const run = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const res = await integrationsApi.upload(file, kind, industry);
      const main = kind === "products" ? res.skus_created : res.sales_rows;
      if (main === 0) {
        // Nothing was imported, even though the request itself returned 200 —
        // this is a failure, not a success. Two cases: an empty/headers-only
        // file (rows_total === 0), or a file whose every row failed to map
        // (e.g. no recognizable SKU/name columns). Surface the actual reason
        // so the user knows what to fix instead of seeing "Imported 0 SKUs".
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
      toast.success(`Imported ${main.toLocaleString()} ${kind === "products" ? "SKUs" : "sales rows"}`);
    } catch {
      /* interceptor surfaces the toast */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <div className="mb-3 flex items-center gap-2.5">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-surface-3 text-content-muted">
          {icon}
        </span>
        <div>
          <h3 className="font-heading text-sm font-semibold tracking-tight text-content">{title}</h3>
          <p className="text-xs text-content-subtle">{description}</p>
        </div>
      </div>

      <FileDropzone file={file} onFile={setFile} hint="CSV or Excel · up to 10 MB" />

      {result && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-surface-2 px-3.5 py-2.5 text-xs">
          <span className="inline-flex items-center gap-1.5 font-medium text-content">
            <CheckCircle2 size={14} className="text-emerald-600" aria-hidden="true" />
            {result.rows_imported.toLocaleString()} of {result.rows_total.toLocaleString()} rows
          </span>
          {kind === "products" ? (
            <span className="font-mono text-content-subtle">
              {result.products_created} products · {result.skus_created} SKUs
            </span>
          ) : (
            <span className="font-mono text-content-subtle">{result.sales_rows} sales rows</span>
          )}
          {result.rows_skipped > 0 && (
            <span className="font-mono text-amber-600">{result.rows_skipped} skipped</span>
          )}
        </div>
      )}

      <div className="mt-3">
        <Button size="sm" variant="secondary" disabled={!file || busy} loading={busy} onClick={run}>
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
