import clsx from "clsx";
import { Boxes, Receipt, Plug } from "@/components/ui/icons";
import {
  forwardRef,
  useImperativeHandle,
  useState,
  type ReactNode,
} from "react";

import { type UploadResult } from "@/api/integrations";
import { ImportUploader } from "@/components/integrations/ImportUploader";
import { OnboardingHelper } from "@/components/ai/OnboardingHelper";
import type { StepHandle, StepProps } from "./types";

type Kind = "products" | "sales";

interface ImportCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  kind: Kind;
  onImported: (kind: Kind, result: UploadResult) => void;
}

const ImportCard = ({ icon, title, description, kind, onImported }: ImportCardProps) => (
  <div className="rounded-2xl border border-line bg-surface p-5">
    <div className="mb-3 flex items-center gap-2.5">
      <span className="text-content-muted">{icon}</span>
      <div><h3 className="font-heading text-sm font-semibold text-content">{title}</h3>
        <p className="text-xs text-content-subtle">{description}</p></div>
    </div>
    <ImportUploader kind={kind} onImported={(result) => onImported(kind, result)} />
  </div>
);

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

      <OnboardingHelper />
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
