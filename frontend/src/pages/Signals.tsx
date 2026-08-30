import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  CloudSun,
  Radio,
  Scale,
  Search,
  Truck,
} from "@/components/ui/icons";
import toast from "react-hot-toast";
import { signalsApi } from "@/api/signals";
import { integrationsApi } from "@/api/integrations";
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
    queryKey: ["signals"],
    queryFn: () => signalsApi.list({ limit: 200 }),
  });

  const {
    data: integrationCatalog,
    isLoading: integrationsLoading,
    isError: integrationsUnavailable,
  } = useQuery({
    queryKey: ["integrations", "catalog"],
    queryFn: integrationsApi.catalog,
  });

  const validate = useMutation({
    mutationFn: (id: string) => signalsApi.validate(id),
    onSuccess: () => {
      toast.success("Signal validated");
      qc.invalidateQueries({ queryKey: ["signals"] });
    },
  });

  if (isLoading) return <PageLoader />;

  const signals = data ?? [];
  const filteredSignals =
    status === "all" ? signals : signals.filter((signal) => signal.status === status);
  const connectedSources =
    integrationCatalog?.groups.flatMap((group) => group.connectors).filter((connector) => connector.connected) ?? [];

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
    <div className="space-y-5">
      <div className="animate-fade-in stagger-1">
        <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-[var(--accent)]">
          <Radio size={14} /> External signals
        </div>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-content">Demand context beyond sales</h1>
        <p className="mt-1 max-w-2xl text-content-subtle">
          Weather, trends, regulatory, logistics — ingested into the forecasting feature store
        </p>
      </div>

      {signals.length > 0 ? (
        <>
          <Card padding="sm" className="animate-fade-in stagger-2">
            <div className="tab-group-container inline-flex max-w-full overflow-x-auto">
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
              data={filteredSignals}
              columns={columns}
              rowKey={(s) => s.id}
              empty={
                <div className="space-y-2">
                  <Radio size={24} className="mx-auto text-content-subtle" />
                  <div className="text-content-subtle">No {status} signals match this filter.</div>
                </div>
              }
            />
          </Card>
        </>
      ) : (
        <SignalsReadiness
          connectedSources={connectedSources.map((source) => source.name)}
          integrationsLoading={integrationsLoading}
          integrationsUnavailable={integrationsUnavailable}
        />
      )}

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

const SIGNAL_EXAMPLES = [
  { icon: Search, label: "Search demand", detail: "Category interest and trend velocity" },
  { icon: CloudSun, label: "Weather events", detail: "Regional conditions that shift demand" },
  { icon: Truck, label: "Supply & logistics", detail: "Delays, capacity, and disruption notices" },
  { icon: Scale, label: "Regulatory updates", detail: "Policy or compliance changes by market" },
] as const;

function SignalsReadiness({
  connectedSources,
  integrationsLoading,
  integrationsUnavailable,
}: {
  connectedSources: string[];
  integrationsLoading: boolean;
  integrationsUnavailable: boolean;
}) {
  const hasConnectedSources = connectedSources.length > 0;
  const sourceSummary =
    connectedSources.length <= 3
      ? connectedSources.join(", ")
      : `${connectedSources.slice(0, 3).join(", ")} +${connectedSources.length - 3} more`;

  return (
    <Card padding="none" className="animate-fade-in stagger-2 overflow-hidden">
      <div className="grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <div className="border-b border-line p-6 lg:border-b-0 lg:border-r">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-surface-3 text-[var(--accent)]">
            <Radio size={20} />
          </div>
          <p className="mt-5 text-[11px] font-bold uppercase tracking-widest text-content-subtle">
            {integrationsLoading
              ? "Checking connected sources"
              : hasConnectedSources
                ? `${connectedSources.length} operational source${connectedSources.length === 1 ? "" : "s"} connected`
                : integrationsUnavailable
                  ? "Signal feed waiting"
                  : "No signal source connected"}
          </p>
          <h2 className="mt-2 font-heading text-xl font-semibold text-content">
            {hasConnectedSources ? "Core data is connected; external signals have not arrived" : "Connect context to your forecasts"}
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-content-muted">
            {hasConnectedSources
              ? `Operational sources: ${sourceSummary}. None has produced an external signal record yet, so this page remains intentionally empty.`
              : "Add a supported source to start collecting external events. Until data arrives, SANKET will not claim any live signal coverage."}
          </p>

          <div className="mt-5 flex flex-wrap gap-2">
            <Link to="/workspace/integrations" className="btn-primary px-4 py-2.5 text-sm">
              {hasConnectedSources ? "Manage sources" : "Open integrations"}
              <ArrowRight size={15} aria-hidden="true" />
            </Link>
            <Link to="/workspace/trends" className="btn-secondary px-4 py-2.5 text-sm">
              Explore market trends
            </Link>
          </div>
        </div>

        <div className="bg-surface-2 p-6">
          <div className="flex items-center justify-between gap-4">
            <h2 className="font-heading text-sm font-semibold text-content">What will appear here</h2>
            <span className="text-[10px] font-bold uppercase tracking-widest text-content-subtle">
              Examples only
            </span>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {SIGNAL_EXAMPLES.map(({ icon: Icon, label, detail }) => (
              <div key={label} className="rounded-2xl border border-line bg-surface p-4">
                <Icon size={17} className="text-[var(--accent)]" aria-hidden="true" />
                <p className="mt-3 text-sm font-semibold text-content">{label}</p>
                <p className="mt-1 text-xs leading-relaxed text-content-subtle">{detail}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
