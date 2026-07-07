import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Radio } from "lucide-react";
import toast from "react-hot-toast";
import { signalsApi } from "@/api/signals";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Table, type Column } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { PageLoader } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { signalStatusColor } from "@/utils/colors";
import { fmtDateTime, fmtRelative } from "@/utils/format";
import type { ExternalSignal, SignalStatus } from "@/types/api";
import clsx from "clsx";

const STATUSES: ("all" | SignalStatus)[] = ["all", "pending", "validated", "rejected", "expired"];

export const SignalsPage = () => {
  const [status, setStatus] = useState<"all" | SignalStatus>("all");
  const [confirmValidateId, setConfirmValidateId] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["signals", status],
    queryFn: () =>
      signalsApi.list({
        status: status === "all" ? undefined : status,
        limit: 200,
      }),
  });

  const validate = useMutation({
    mutationFn: (id: string) => signalsApi.validate(id),
    onSuccess: () => {
      toast.success("Signal validated");
      qc.invalidateQueries({ queryKey: ["signals"] });
    },
  });

  if (isLoading) return <PageLoader />;

  const columns: Column<ExternalSignal>[] = [
    {
      key: "type",
      header: "Type",
      render: (s) => (
        <Badge variant="info">
          <span className="capitalize">{s.signal_type.replace(/_/g, " ")}</span>
        </Badge>
      ),
    },
    {
      key: "source",
      header: "Source",
      render: (s) => (
        <div>
          <div className="text-slate-700">{s.source_name}</div>
          {s.region && <div className="text-xs text-slate-400">{s.region}</div>}
        </div>
      ),
    },
    {
      key: "effective",
      header: "Effective",
      render: (s) => (
        <span className="text-slate-500" title={fmtDateTime(s.effective_at)}>
          {fmtRelative(s.effective_at)}
        </span>
      ),
    },
    {
      key: "impact",
      header: "Impact",
      align: "right",
      render: (s) =>
        s.impact_weight != null ? (
          <Badge
            variant={
              s.impact_weight >= 0.7 ? "danger" : s.impact_weight >= 0.4 ? "warning" : "default"
            }
          >
            {(s.impact_weight * 100).toFixed(0)}%
          </Badge>
        ) : (
          <span className="text-slate-400">—</span>
        ),
    },
    {
      key: "status",
      header: "Status",
      render: (s) => (
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
            signalStatusColor[s.status],
          )}
        >
          {s.status}
        </span>
      ),
    },
    {
      key: "action",
      header: "",
      align: "right",
      render: (s) =>
        s.status === "pending" ? (
          <Button
            size="sm"
            variant="secondary"
            icon={<CheckCircle2 size={13} />}
            onClick={() => setConfirmValidateId(s.id)}
          >
            Validate
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="animate-fade-in stagger-1">
        <h1 className="text-3xl font-bold tracking-tight text-slate-800">External Signals</h1>
        <p className="text-slate-500 mt-1">
          Weather, trends, regulatory, logistics — ingested into the forecasting feature store
        </p>
      </div>

      <Card padding="sm" className="animate-fade-in stagger-2">
        <div className="tab-group-container inline-flex">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={status === s ? "tab-item-active" : "tab-item-inactive"}
            >
              {s === "all" ? "All signals" : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </Card>

      <Card padding="sm" className="animate-fade-in stagger-3">
        <Table
          data={data ?? []}
          columns={columns}
          rowKey={(s) => s.id}
          empty={
            <div className="space-y-2">
              <Radio size={28} className="mx-auto text-slate-400" />
              <div className="text-slate-500">No signals match this filter.</div>
            </div>
          }
        />
      </Card>

      <ConfirmDialog
        open={!!confirmValidateId}
        title="Validate signal?"
        message={
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Validating this signal marks it as confirmed and incorporates it into the next
            forecast run. This action cannot be undone.
          </p>
        }
        confirmLabel="Validate signal"
        tone="primary"
        loading={validate.isPending}
        onConfirm={() => {
          if (confirmValidateId) validate.mutate(confirmValidateId);
          setConfirmValidateId(null);
        }}
        onClose={() => setConfirmValidateId(null)}
      />
    </div>
  );
};
