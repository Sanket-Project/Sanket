import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Webhook,
  Plus,
  RefreshCw,
  Trash2,
  Copy,
  Check,
  Server,
  Code,
  Terminal,
  Activity,
  Calendar,
  AlertCircle,
  Play
} from "lucide-react";
import toast from "react-hot-toast";
import {
  webhooksApi,
  WEBHOOK_EVENT_TYPES,
  type WebhookEndpoint,
  type WebhookDelivery,
} from "@/api/webhooks";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Table, type Column } from "@/components/ui/Table";
import { PageLoader } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { fmtRelative, fmtDateTime } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";

const STATUS_VARIANT: Record<
  WebhookDelivery["status"],
  "success" | "warning" | "danger" | "default"
> = {
  pending: "warning",
  succeeded: "success",
  failed: "danger",
  dead_letter: "danger",
};

const CopyButton = ({ text, className = "" }: { text: string; className?: string }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className={`p-1.5 rounded-lg text-slate-400 hover:text-violet-600 hover:bg-violet-50 border border-transparent hover:border-violet-100 transition-all duration-200 active:scale-90 ${className}`}
      title="Copy to clipboard"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
};

export const WebhooksPage = () => {
  const qc = useQueryClient();
  const [openCreate, setOpenCreate] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [revealedSecret, setRevealedSecret] = useState<{ id: string; secret: string } | null>(null);
  const [selectedDelivery, setSelectedDelivery] = useState<WebhookDelivery | null>(null);
  const [activeTab, setActiveTab] = useState<"payload" | "response">("payload");

  const { data: endpoints, isLoading: l1 } = useQuery({
    queryKey: ["webhooks", "endpoints"],
    queryFn: webhooksApi.list,
  });
  const { data: deliveries } = useQuery({
    queryKey: ["webhooks", "deliveries"],
    queryFn: () => webhooksApi.deliveries({ limit: 50 }),
    refetchInterval: 15_000,
  });

  const create = useMutation({
    mutationFn: webhooksApi.create,
    onSuccess: (r) => {
      toast.success("Webhook endpoint created");
      setRevealedSecret({ id: r.id, secret: r.secret });
      qc.invalidateQueries({ queryKey: ["webhooks"] });
      setOpenCreate(false);
    },
    onError: (e: unknown) => {
      toast.error(getErrorMessage(e, "Failed to create endpoint"));
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => webhooksApi.remove(id),
    onSuccess: () => {
      toast.success("Endpoint removed");
      qc.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });

  const retry = useMutation({
    mutationFn: (id: number) => webhooksApi.retry(id),
    onSuccess: () => {
      toast.success("Retry queued successfully");
      qc.invalidateQueries({ queryKey: ["webhooks"] });
      // If we are looking at the details modal of the delivery we just retried, close it or refresh active status
      setSelectedDelivery(null);
    },
  });

  if (l1) return <PageLoader />;

  const endpointCols: Column<WebhookEndpoint>[] = [
    {
      key: "url",
      header: "Endpoint URL",
      render: (e) => (
        <div className="flex items-center gap-2 group max-w-[480px]">
          <div className="h-8 w-8 rounded-lg bg-slate-50 border border-slate-200/60 flex items-center justify-center shrink-0 text-slate-400 group-hover:text-violet-600 transition-colors">
            <Server size={14} />
          </div>
          <div className="truncate flex-1">
            <div className="font-mono text-xs text-slate-700 font-semibold truncate hover:text-slate-900">
              {e.url}
            </div>
            {e.description && (
              <div className="text-xs text-slate-400 mt-0.5 font-medium">{e.description}</div>
            )}
          </div>
          <CopyButton text={e.url} className="opacity-0 group-hover:opacity-100 shrink-0" />
        </div>
      ),
    },
    {
      key: "events",
      header: "Subscribed Events",
      render: (e) => (
        <div className="flex flex-wrap gap-1 max-w-[280px]">
          {e.enabled_events.slice(0, 2).map((ev) => (
            <Badge key={ev} variant="primary" className="font-mono text-[9px]">
              {ev.split(".")[1] || ev}
            </Badge>
          ))}
          {e.enabled_events.length > 2 && (
            <Badge variant="default" className="font-mono text-[9px] bg-slate-50 text-slate-500">
              +{e.enabled_events.length - 2} more
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (e) =>
        e.is_active ? (
          <Badge variant="success">Active</Badge>
        ) : (
          <Badge variant="warning">Paused</Badge>
        ),
    },
    {
      key: "failures",
      header: "Failures",
      align: "center",
      render: (e) =>
        e.failure_count > 0 ? (
          <Badge variant="danger" className="animate-pulse">
            {e.failure_count}
          </Badge>
        ) : (
          <span className="text-slate-400 text-xs font-semibold">0</span>
        ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (e) => (
        <Button
          variant="ghost"
          size="sm"
          icon={<Trash2 size={13} />}
          className="text-slate-400 hover:text-rose-600 hover:bg-rose-50/50 border border-transparent hover:border-rose-100 transition-colors"
          onClick={(ev) => {
            ev.stopPropagation();
            setConfirmDeleteId(e.id);
          }}
        >
          Delete
        </Button>
      ),
    },
  ];

  const deliveryCols: Column<WebhookDelivery>[] = [
    {
      key: "event",
      header: "Event Trigger",
      render: (d) => (
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-violet-400 shrink-0" />
          <span className="font-mono text-xs font-semibold text-slate-700">{d.event_type}</span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Delivery Status",
      render: (d) => <Badge variant={STATUS_VARIANT[d.status]}>{d.status}</Badge>,
    },
    {
      key: "attempts",
      header: "Attempts",
      align: "center",
      render: (d) => <span className="font-mono text-xs font-semibold text-slate-600">{d.attempt_count}</span>,
    },
    {
      key: "response",
      header: "Response Code",
      render: (d) =>
        d.response_status != null ? (
          <Badge
            variant={
              d.response_status < 300
                ? "success"
                : d.response_status < 500
                ? "warning"
                : "danger"
            }
            className="font-mono"
          >
            HTTP {d.response_status}
          </Badge>
        ) : (
          <span className="text-slate-400 text-xs font-medium">—</span>
        ),
    },
    {
      key: "when",
      header: "Delivered",
      render: (d) => (
        <span
          title={fmtDateTime(d.delivered_at ?? d.created_at)}
          className="text-slate-400 text-xs font-medium"
        >
          {fmtRelative(d.delivered_at ?? d.created_at)}
        </span>
      ),
    },
    {
      key: "retry",
      header: "",
      align: "right",
      render: (d) =>
        d.status === "failed" || d.status === "dead_letter" ? (
          <Button
            size="sm"
            variant="secondary"
            icon={<RefreshCw size={12} />}
            loading={retry.isPending}
            className="h-8"
            onClick={(ev) => {
              ev.stopPropagation();
              retry.mutate(d.id);
            }}
          >
            Retry
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header section */}
      <div className="flex items-center justify-between animate-fade-in stagger-1 bg-white/70 border border-slate-200/60 p-6 rounded-2xl shadow-sm backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-2xl bg-violet-50 border border-violet-200/60 flex items-center justify-center text-violet-600 shadow-inner shrink-0">
            <Webhook size={24} className="animate-pulse" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-800">Webhooks</h1>
            <p className="text-slate-500 mt-0.5 text-sm">
              Manage developer endpoint routes, monitor live telemetry, and review delivery history.
            </p>
          </div>
        </div>
        <Button icon={<Plus size={15} />} onClick={() => setOpenCreate(true)}>
          New Endpoint
        </Button>
      </div>

      {/* Webhook Endpoints List Card */}
      <Card
        padding="sm"
        className="animate-fade-in stagger-2 shadow-sm"
        title={
          <div className="flex items-center gap-2">
            <Server size={16} className="text-slate-400" />
            <span>Active Integrations</span>
            <Badge variant="primary" className="ml-1 text-[9px] py-0.5 px-2">
              {endpoints?.length ?? 0}
            </Badge>
          </div>
        }
      >
        <Table
          data={endpoints ?? []}
          columns={endpointCols}
          rowKey={(e) => e.id}
          empty={
            <div className="py-6 text-center text-slate-400 text-sm font-medium">
              No webhook endpoints configured yet.
            </div>
          }
        />
      </Card>

      {/* Deliveries Card */}
      <Card
        padding="sm"
        className="animate-fade-in stagger-3 shadow-sm"
        title={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-2">
              <Activity size={16} className="text-slate-400" />
              <span>Real-time Deliveries</span>
            </div>
            <span className="text-[10px] text-slate-400 font-semibold tracking-wider uppercase bg-slate-50 border border-slate-100 rounded-lg px-2.5 py-1">
              Click row to inspect payload
            </span>
          </div>
        }
      >
        <Table
          data={deliveries ?? []}
          columns={deliveryCols}
          rowKey={(d) => String(d.id)}
          onRowClick={(d) => {
            setSelectedDelivery(d);
            setActiveTab("payload");
          }}
          empty={
            <div className="py-6 text-center text-slate-400 text-sm font-medium">
              No webhook deliveries recorded yet.
            </div>
          }
        />
      </Card>

      {/* Modal - Create Endpoint */}
      <CreateModal
        open={openCreate}
        onClose={() => setOpenCreate(false)}
        onSubmit={(body) => create.mutate(body)}
        pending={create.isPending}
      />

      {/* Modal - Save Secret (Only Shown Once) */}
      <Modal
        open={!!revealedSecret}
        onClose={() => setRevealedSecret(null)}
        title={
          <div className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-emerald-50 border border-emerald-200/50 flex items-center justify-center text-emerald-600">
              <Check size={14} className="stroke-[3]" />
            </div>
            <span className="font-bold text-slate-800">Signing Secret Generated</span>
          </div>
        }
        footer={
          <Button onClick={() => setRevealedSecret(null)}>I've Saved It Safely</Button>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600 leading-relaxed">
            This secret signature will **only be shown once**. Copy and save it immediately to securely verify the HMAC signature header on incoming payloads.
          </p>

          <div className="bg-slate-50 border border-slate-200/80 p-3 rounded-xl flex items-center justify-between gap-3 shadow-inner">
            <span className="font-mono text-xs text-slate-800 font-semibold truncate select-all">
              {revealedSecret?.secret}
            </span>
            <CopyButton text={revealedSecret?.secret ?? ""} className="bg-white hover:bg-violet-100 shadow-sm border border-slate-200" />
          </div>

          <div className="flex gap-2.5 items-start bg-amber-50 border border-amber-200/50 p-3.5 rounded-xl text-xs text-amber-800 font-medium leading-relaxed">
            <AlertCircle size={15} className="shrink-0 mt-0.5 text-amber-600" />
            <div>
              Verification header format is: <code className="bg-amber-100/70 border border-amber-200 px-1 py-0.5 rounded font-mono text-[10px]">X-Sanket-Signature</code>. Use your endpoint code to recalculate the HMAC SHA256 hex digest using this key.
            </div>
          </div>
        </div>
      </Modal>

      {/* Modal - Interactive Delivery Payload Drawer */}
      <Modal
        open={!!selectedDelivery}
        onClose={() => setSelectedDelivery(null)}
        size="lg"
        title={
          selectedDelivery && (
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 rounded-lg bg-slate-50 border border-slate-200/50 flex items-center justify-center text-slate-400">
                <Code size={15} />
              </div>
              <div>
                <span className="font-bold text-slate-800 tracking-tight text-lg">Delivery Inspector</span>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                  ID: {selectedDelivery.event_id}
                </div>
              </div>
            </div>
          )
        }
        footer={
          selectedDelivery && (
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-1.5">
                <Calendar size={13} className="text-slate-400" />
                <span className="text-xs text-slate-500 font-medium">
                  {fmtDateTime(selectedDelivery.created_at)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {(selectedDelivery.status === "failed" || selectedDelivery.status === "dead_letter") && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<Play size={12} />}
                    loading={retry.isPending}
                    onClick={() => retry.mutate(selectedDelivery.id)}
                  >
                    Re-deliver Payload
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={() => setSelectedDelivery(null)}>
                  Close
                </Button>
              </div>
            </div>
          )
        }
      >
        {selectedDelivery && (
          <div className="space-y-4 animate-fade-in">
            {/* Status overview badges */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-50 border border-slate-200/50 p-2.5 rounded-xl">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Event Trigger</div>
                <div className="text-xs font-mono font-bold text-slate-700 mt-1 truncate">
                  {selectedDelivery.event_type}
                </div>
              </div>
              <div className="bg-slate-50 border border-slate-200/50 p-2.5 rounded-xl">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Status</div>
                <div className="mt-1">
                  <Badge variant={STATUS_VARIANT[selectedDelivery.status]} className="text-[9px]">
                    {selectedDelivery.status}
                  </Badge>
                </div>
              </div>
              <div className="bg-slate-50 border border-slate-200/50 p-2.5 rounded-xl">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Attempt Count</div>
                <div className="text-xs font-bold text-slate-700 mt-1">
                  {selectedDelivery.attempt_count} / 5
                </div>
              </div>
              <div className="bg-slate-50 border border-slate-200/50 p-2.5 rounded-xl">
                <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Response Status</div>
                <div className="mt-1">
                  {selectedDelivery.response_status != null ? (
                    <Badge
                      variant={selectedDelivery.response_status < 300 ? "success" : "danger"}
                      className="text-[9px] font-mono"
                    >
                      HTTP {selectedDelivery.response_status}
                    </Badge>
                  ) : (
                    <span className="text-xs font-semibold text-slate-400">NONE</span>
                  )}
                </div>
              </div>
            </div>

            {/* Custom Tab selectors */}
            <div className="tab-group-container my-3">
              <div
                onClick={() => setActiveTab("payload")}
                className={activeTab === "payload" ? "tab-item-active flex-1 text-center" : "tab-item-inactive flex-1 text-center"}
              >
                <div className="flex items-center justify-center gap-1.5">
                  <Terminal size={12} />
                  <span>Request JSON Payload</span>
                </div>
              </div>
              <div
                onClick={() => setActiveTab("response")}
                className={activeTab === "response" ? "tab-item-active flex-1 text-center" : "tab-item-inactive flex-1 text-center"}
              >
                <div className="flex items-center justify-center gap-1.5">
                  <Code size={12} />
                  <span>Response Header Body</span>
                </div>
              </div>
            </div>

            {/* Content areas */}
            {activeTab === "payload" ? (
              <div className="relative group">
                <div className="absolute top-3 right-3 z-10">
                  <CopyButton
                    text={JSON.stringify(selectedDelivery.payload, null, 2)}
                    className="bg-slate-800/80 border border-slate-700/80 hover:bg-slate-700/90 text-slate-300 hover:text-white backdrop-blur shadow-md"
                  />
                </div>
                <pre className="bg-slate-950 text-slate-200 font-mono text-xs p-4 rounded-xl max-h-[350px] overflow-auto border border-slate-800/90 shadow-2xl">
                  {JSON.stringify(selectedDelivery.payload, null, 2)}
                </pre>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-1">Raw Response Body</div>
                {selectedDelivery.response_body ? (
                  <pre className="bg-slate-900 text-rose-300 border border-slate-800 font-mono text-xs p-4 rounded-xl max-h-[350px] overflow-auto">
                    {selectedDelivery.response_body}
                  </pre>
                ) : (
                  <div className="border border-slate-200/60 rounded-xl bg-slate-50/50 p-8 text-center text-slate-400 text-sm font-semibold">
                    No response headers or body were received back from your webhook endpoint.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={!!confirmDeleteId}
        title="Delete webhook endpoint?"
        message={
          <p className="text-sm text-slate-600 dark:text-slate-400">
            This will permanently remove the endpoint and stop all future deliveries. In-flight
            deliveries will not be retried.
          </p>
        }
        confirmLabel="Delete endpoint"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => {
          if (confirmDeleteId) remove.mutate(confirmDeleteId);
          setConfirmDeleteId(null);
        }}
        onClose={() => setConfirmDeleteId(null)}
      />
    </div>
  );
};

const CreateModal = ({
  open,
  onClose,
  onSubmit,
  pending,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: { url: string; enabled_events: string[]; description?: string }) => void;
  pending: boolean;
}) => {
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = (ev: string) =>
    setSelected((s) =>
      s.includes(ev) ? s.filter((e) => e !== ev) : [...s, ev],
    );

  const selectAll = () => setSelected([...WEBHOOK_EVENT_TYPES]);
  const selectNone = () => setSelected([]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-violet-50 border border-violet-200/50 flex items-center justify-center text-violet-600">
            <Webhook size={16} />
          </div>
          <span className="font-bold text-slate-800">Add Webhook Endpoint</span>
        </div>
      }
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} size="sm">
            Cancel
          </Button>
          <Button
            loading={pending}
            disabled={!url || selected.length === 0 || !url.startsWith("https://")}
            onClick={() =>
              onSubmit({
                url,
                enabled_events: selected,
                description: description || undefined,
              })
            }
            size="sm"
          >
            Create Connection
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Endpoint URL (HTTPS only)"
          placeholder="https://your-domain.com/webhooks/sanket"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Input
          label="Description"
          placeholder="Describe when and how this consumer route is triggered"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        
        <div>
          <div className="flex justify-between items-center mb-2">
            <label className="label mb-0">Subscribe to Event Triggers</label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={selectAll}
                className="text-[10px] text-violet-600 font-bold hover:text-violet-700 bg-violet-50 hover:bg-violet-100 px-2 py-1 rounded-md transition"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={selectNone}
                className="text-[10px] text-slate-500 font-bold hover:text-slate-700 bg-slate-100 hover:bg-slate-200 px-2 py-1 rounded-md transition"
              >
                Clear
              </button>
            </div>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
            {WEBHOOK_EVENT_TYPES.map((ev) => {
              const isSelected = selected.includes(ev);
              return (
                <label
                  key={ev}
                  className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border cursor-pointer transition-all duration-200 hover:-translate-y-px select-none active:scale-[0.985] ${
                    isSelected
                      ? "bg-violet-50/70 border-violet-300 text-violet-900 shadow-sm"
                      : "bg-white border-slate-200 hover:bg-slate-50 text-slate-600"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isSelected}
                    onChange={() => toggle(ev)}
                  />
                  <div className={`h-4.5 w-4.5 rounded-md border flex items-center justify-center transition-colors ${
                    isSelected ? "bg-violet-600 border-violet-600 text-white" : "border-slate-300 bg-white"
                  }`}>
                    {isSelected && <Check size={12} className="stroke-[3.5]" />}
                  </div>
                  <span className="font-mono text-xs font-semibold tracking-tight">{ev}</span>
                </label>
              );
            })}
          </div>
        </div>
      </div>
    </Modal>
  );
};
