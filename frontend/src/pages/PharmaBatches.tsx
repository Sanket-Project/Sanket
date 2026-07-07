import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Lock } from "lucide-react";
import toast from "react-hot-toast";
import { pharmaApi } from "@/api/pharma";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Table, type Column } from "@/components/ui/Table";
import { PageLoader } from "@/components/ui/Spinner";
import { fmtCompact, fmtDate } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import { useAuthStore } from "@/stores/auth";
import { useIndustryStore } from "@/stores/industry";
import type { PharmaBatchExpiring } from "@/types/api";

export const PharmaBatchesPage = () => {
  const role = useAuthStore((s) => s.role);
  const activeIndustry = useIndustryStore((s) => s.activeIndustry);
  const [days, setDays] = useState(90);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["pharma-expiring", days],
    queryFn: () => pharmaApi.expiringBatches(days),
  });

  const release = useMutation({
    mutationFn: (id: string) => pharmaApi.releaseBatch(id),
    onSuccess: (r) => {
      toast.success(`Batch ${r.lot_number} released`);
      qc.invalidateQueries({ queryKey: ["pharma-expiring"] });
      qc.invalidateQueries({ queryKey: ["pharma-overview"] });
      setConfirmingId(null);
    },
    onError: (e: unknown) => {
      toast.error(getErrorMessage(e, "Release failed"));
    },
  });

  if (isLoading) return <PageLoader />;

  if (activeIndustry !== "pharma") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4 text-center p-8">
        <div className="h-16 w-16 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
          <Lock size={28} className="text-slate-400" />
        </div>
        <h2 className="text-xl font-bold text-slate-700 dark:text-slate-200">
          Pharma industry required
        </h2>
        <p className="text-slate-500 dark:text-slate-400 max-w-md">
          GxP Batch management is only available when your workspace is configured for the
          Pharmaceutical industry. Switch your active industry context to access this module.
        </p>
      </div>
    );
  }

  const canRelease = role === "owner" || role === "admin";

  const cols: Column<PharmaBatchExpiring>[] = [
    {
      key: "lot",
      header: "Lot Number",
      render: (b) => <span className="font-mono text-xs">{b.lot_number}</span>,
    },
    { key: "ndc", header: "NDC", render: (b) => b.ndc_code ?? "—" },
    {
      key: "expiry",
      header: "Expiry",
      render: (b) => {
        const ms = new Date(b.expiry_date).getTime() - Date.now();
        const dleft = Math.floor(ms / 86_400_000);
        return (
          <Badge variant={dleft < 30 ? "danger" : dleft < 60 ? "warning" : "info"}>
            {fmtDate(b.expiry_date)} ({dleft}d)
          </Badge>
        );
      },
    },
    {
      key: "qty",
      header: "Qty Remaining",
      align: "right",
      render: (b) => fmtCompact(b.quantity_remaining),
    },
    {
      key: "cc",
      header: "Cold Chain",
      align: "center",
      render: (b) => (b.cold_chain_required ? <Badge variant="info">Required</Badge> : "—"),
    },
    {
      key: "action",
      header: "",
      align: "right",
      render: (b) =>
        canRelease ? (
          <Button
            size="sm"
            variant="secondary"
            icon={<ShieldCheck size={13} />}
            onClick={() => setConfirmingId(b.id)}
          >
            QA Release
          </Button>
        ) : (
          <Badge>View only</Badge>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3 text-slate-800">
            GxP Batches
            <Badge variant="success">21 CFR Part 11</Badge>
          </h1>
          <p className="text-slate-500 mt-1">
            Pharma batch traceability — every action is written to the immutable audit log
          </p>
        </div>
        <div className="flex gap-2">
          {[30, 60, 90, 180].map((d) => (
            <Button
              key={d}
              size="sm"
              variant={days === d ? "primary" : "secondary"}
              onClick={() => setDays(d)}
            >
              ≤ {d}d
            </Button>
          ))}
        </div>
      </div>

      <Card padding="sm" title={`${data?.count ?? 0} batches expiring within ${days} days`}>
        <Table
          data={data?.batches ?? []}
          columns={cols}
          rowKey={(b) => b.id}
          empty="No batches at expiry risk in this window."
        />
      </Card>

      <Modal
        open={!!confirmingId}
        onClose={() => setConfirmingId(null)}
        title="Confirm QA Release"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmingId(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={release.isPending}
              onClick={() => confirmingId && release.mutate(confirmingId)}
            >
              Release batch
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          You are about to release this batch from quarantine to <b>RELEASED</b> status. This
          action requires QA authorization and will be recorded in the GxP audit trail with
          your user ID, IP, and timestamp.
        </p>
        <p className="text-xs text-slate-400 mt-3">
          Cold-chain temperature records must be present for cold-chain batches; the server
          will reject the release otherwise.
        </p>
      </Modal>
    </div>
  );
};
