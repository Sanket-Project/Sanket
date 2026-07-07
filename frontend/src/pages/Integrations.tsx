import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Boxes,
  Building2,
  CheckCircle2,
  Clock,
  CreditCard,
  Database,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Link2,
  Package,
  Plug,
  Radio,
  Receipt,
  RefreshCw,
  ShoppingBag,
  ShoppingCart,
  Unlink,
  Upload,
  Warehouse,
  Webhook,
  type LucideIcon,
} from "lucide-react";
import toast from "react-hot-toast";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { PageLoader } from "@/components/ui/Spinner";
import {
  integrationsApi,
  type Connector,
  type IntegrationStatus,
} from "@/api/integrations";
import { industryDisplay } from "@/utils/colors";
import { useIndustryStore } from "@/stores/industry";
import { fmtRelative } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import type { IndustryCode } from "@/types/api";

const ICONS: Record<string, LucideIcon> = {
  "file-text": FileText,
  "file-spreadsheet": FileSpreadsheet,
  webhook: Webhook,
  "shopping-bag": ShoppingBag,
  "shopping-cart": ShoppingCart,
  package: Package,
  "credit-card": CreditCard,
  "building-2": Building2,
  warehouse: Warehouse,
  radio: Radio,
  database: Database,
  plug: Plug,
};

const FEED_ICONS: Record<string, LucideIcon> = {
  sales: Receipt,
  inventory: Boxes,
  products: Package,
  warehouse: Warehouse,
  purchase_orders: Receipt,
};

function IndustrySelect({
  value,
  onChange,
}: {
  value: IndustryCode;
  onChange: (v: IndustryCode) => void;
}) {
  return (
    <div className="w-full">
      <label className="label">Target industry</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value as IndustryCode)}>
        {(Object.keys(industryDisplay) as IndustryCode[]).map((code) => (
          <option key={code} value={code}>
            {industryDisplay[code]}
          </option>
        ))}
      </select>
    </div>
  );
}

function availabilityBadge(a: Connector["availability"]) {
  if (a === "live") return <Badge variant="success" dot>Live</Badge>;
  if (a === "beta") return <Badge variant="info" dot>Beta</Badge>;
  return <Badge variant="default">Coming soon</Badge>;
}

function statusBadge(status: string) {
  const map: Record<string, { v: "success" | "warning" | "danger" | "info" | "default"; label: string }> = {
    connected: { v: "success", label: "Connected" },
    syncing: { v: "warning", label: "Syncing" },
    error: { v: "danger", label: "Error" },
    requested: { v: "info", label: "Requested" },
  };
  const s = map[status];
  if (!s) return null;
  return (
    <Badge variant={s.v} dot>
      {status === "syncing" && <RefreshCw size={10} className="animate-spin" />}
      {s.label}
    </Badge>
  );
}

// ── Connector card ────────────────────────────────────────────────────────────
function ConnectorCard({ c, onOpen }: { c: Connector; onOpen: (c: Connector) => void }) {
  const Icon = ICONS[c.icon] ?? Plug;
  return (
    <button
      onClick={() => onOpen(c)}
      className="text-left group rounded-2xl border border-line bg-surface hover:border-[var(--accent)]/40 hover:shadow-md transition-all p-4 flex flex-col gap-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className={`h-11 w-11 rounded-xl flex items-center justify-center text-white shrink-0 bg-gradient-to-br ${c.accent} shadow`}>
          <Icon size={20} />
        </div>
        <div className="flex flex-col items-end gap-1">
          {statusBadge(c.status)}
          {!c.connected && c.status !== "requested" && availabilityBadge(c.availability)}
        </div>
      </div>
      <div>
        <h3 className="font-semibold text-content tracking-tight">{c.name}</h3>
        <p className="text-xs text-content-muted mt-1 line-clamp-2 leading-relaxed">{c.summary}</p>
      </div>
      <div className="flex flex-wrap gap-1.5 mt-auto pt-1">
        {c.feeds.map((f) => {
          const FI = FEED_ICONS[f] ?? Boxes;
          return (
            <span key={f} className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-content-subtle bg-surface-2 border border-line rounded-md px-1.5 py-0.5">
              <FI size={10} /> {f.replace("_", " ")}
            </span>
          );
        })}
      </div>
    </button>
  );
}

// ── File upload panel ─────────────────────────────────────────────────────────
const UPLOAD_KINDS = [
  { key: "sales", label: "Sales history", cols: "SKU, Quantity, Selling Price, Timestamp" },
  { key: "inventory", label: "Inventory levels", cols: "SKU, Available Stock, Warehouse" },
  { key: "products", label: "Product catalog", cols: "SKU, Name, Category, Price" },
] as const;

function UploadPanel({ defaultIndustry, onDone }: { defaultIndustry: IndustryCode; onDone: () => void }) {
  const [kind, setKind] = useState<(typeof UPLOAD_KINDS)[number]["key"]>("sales");
  const [industry, setIndustry] = useState<IndustryCode>(defaultIndustry);
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = useMutation({
    mutationFn: () => integrationsApi.upload(file as File, kind, industry),
    onSuccess: (r) => {
      toast.success(`Imported ${r.rows_imported} of ${r.rows_total} rows`);
      onDone();
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Upload failed")),
  });

  const expected = UPLOAD_KINDS.find((k) => k.key === kind)!.cols;

  return (
    <div className="space-y-4">
      <div>
        <label className="label">What are you importing?</label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {UPLOAD_KINDS.map((k) => (
            <button
              key={k.key}
              onClick={() => setKind(k.key)}
              className={`p-2.5 rounded-xl border text-xs font-semibold transition-colors ${
                kind === k.key
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-line text-content-muted hover:bg-surface-2"
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>
      </div>

      <IndustrySelect value={industry} onChange={setIndustry} />

      <div>
        <label className="label">File (.csv or .xlsx)</label>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.xlsm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="hidden"
        />
        <button
          onClick={() => fileRef.current?.click()}
          className="w-full rounded-xl border border-dashed border-line hover:border-[var(--accent)]/50 bg-surface-2 px-4 py-6 flex flex-col items-center gap-2 text-content-muted transition-colors"
        >
          <Upload size={22} />
          <span className="text-sm font-medium">{file ? file.name : "Click to choose a file"}</span>
          <span className="text-[11px] text-content-subtle">Expected columns: {expected}</span>
        </button>
      </div>

      <div className="rounded-xl bg-surface-2 border border-line p-3 text-[11px] text-content-subtle leading-relaxed">
        Columns are auto-mapped — common header names like "qty", "units", "price" and "date" are
        recognized. Unmatched or invalid rows are skipped and reported.
      </div>

      <Button
        variant="primary"
        icon={<Upload size={15} />}
        loading={upload.isPending}
        disabled={!file}
        onClick={() => upload.mutate()}
        className="w-full justify-center"
      >
        Import file
      </Button>
    </div>
  );
}

// ── Generic credential / request panel ────────────────────────────────────────
function CredentialPanel({ connector, defaultIndustry, onDone }: { connector: Connector; defaultIndustry: IndustryCode; onDone: () => void }) {
  const [industry, setIndustry] = useState<IndustryCode>(defaultIndustry);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const isPlanned = connector.availability === "planned";

  const connect = useMutation({
    mutationFn: () => integrationsApi.connect(connector.key, { target_industry: industry, credentials: creds }),
    onSuccess: () => {
      toast.success(
        isPlanned
          ? `Request received — we'll enable ${connector.name} for your account`
          : `${connector.name} connected`,
      );
      onDone();
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Could not connect")),
  });

  const missingRequired = connector.auth_fields.some((f) => f.required && !creds[f.key]?.trim());

  return (
    <div className="space-y-4">
      {isPlanned && (
        <div className="rounded-xl bg-cyan-50/60 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/30 p-3 text-xs text-cyan-800 dark:text-cyan-300 leading-relaxed">
          A managed sync for {connector.name} isn't live yet. Submit your details and we'll provision
          it for your account — your credentials are encrypted at rest.
        </div>
      )}
      <IndustrySelect value={industry} onChange={setIndustry} />
      {connector.auth_fields.map((f) =>
        f.type === "textarea" ? (
          <div key={f.key} className="w-full">
            <label className="label">{f.label}{!f.required && " (optional)"}</label>
            <textarea
              className="input min-h-[90px] font-mono text-xs"
              placeholder={f.placeholder ?? ""}
              value={creds[f.key] ?? ""}
              onChange={(e) => setCreds((s) => ({ ...s, [f.key]: e.target.value }))}
            />
            {f.help && <p className="text-[11px] text-content-subtle mt-1">{f.help}</p>}
          </div>
        ) : (
          <Input
            key={f.key}
            label={`${f.label}${!f.required ? " (optional)" : ""}`}
            name={f.key}
            type={f.secret ? "password" : f.type === "url" ? "url" : "text"}
            placeholder={f.placeholder ?? ""}
            hint={f.help ?? undefined}
            value={creds[f.key] ?? ""}
            onChange={(e) => setCreds((s) => ({ ...s, [f.key]: e.target.value }))}
          />
        ),
      )}
      <Button
        variant="primary"
        icon={<Link2 size={15} />}
        loading={connect.isPending}
        disabled={missingRequired}
        onClick={() => connect.mutate()}
        className="w-full justify-center"
      >
        {isPlanned ? "Request integration" : `Connect ${connector.name}`}
      </Button>
      {connector.docs_url && (
        <a href={connector.docs_url} target="_blank" rel="noreferrer" className="text-xs font-semibold text-[var(--accent)] inline-flex items-center gap-1">
          Setup guide <ExternalLink size={11} />
        </a>
      )}
    </div>
  );
}

// ── Push panel (rest_api / webhooks) ──────────────────────────────────────────
function PushPanel({ connector, defaultIndustry, onDone }: { connector: Connector; defaultIndustry: IndustryCode; onDone: () => void }) {
  const [industry, setIndustry] = useState<IndustryCode>(defaultIndustry);
  const [token, setToken] = useState<string | null>(null);
  const endpoint = `${window.location.origin}/api/v1/integrations/ingest`;

  const connect = useMutation({
    mutationFn: () => integrationsApi.connect(connector.key, { target_industry: industry, credentials: {} }),
    onSuccess: (c) => {
      setToken(c.push_token ?? null);
      toast.success(`${connector.name} enabled`);
      onDone();
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Could not enable")),
  });

  if (token) {
    return (
      <div className="space-y-4">
        <div className="rounded-xl bg-amber-50/60 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 p-3 text-xs text-amber-800 dark:text-amber-300">
          Copy your push token now — it's shown only once and stored hashed.
        </div>
        <div>
          <label className="label">Push token</label>
          <code className="block w-full rounded-lg bg-surface-2 border border-line px-3 py-2 text-xs break-all font-mono">{token}</code>
        </div>
        <div>
          <label className="label">Endpoint</label>
          <code className="block w-full rounded-lg bg-surface-2 border border-line px-3 py-2 text-xs break-all font-mono">POST {endpoint}</code>
        </div>
        <div>
          <label className="label">Example</label>
          <pre className="rounded-lg bg-surface-2 border border-line p-3 text-[11px] overflow-x-auto font-mono leading-relaxed">{`curl -X POST ${endpoint} \\
  -H "X-Sanket-Token: ${token.slice(0, 8)}…" \\
  -H "Content-Type: application/json" \\
  -d '{"sku":"SKU001","quantity":2,"revenue":2500,
       "timestamp":"${new Date().toISOString()}","channel":"pos"}'`}</pre>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-content-muted">
        Enable a token-authenticated endpoint to push canonical sale events from any system. Events
        appear instantly on Live Sales and feed forecasting.
      </p>
      <IndustrySelect value={industry} onChange={setIndustry} />
      <Button
        variant="primary"
        icon={<Webhook size={15} />}
        loading={connect.isPending}
        onClick={() => connect.mutate()}
        className="w-full justify-center"
      >
        Enable {connector.name}
      </Button>
    </div>
  );
}

// ── Shopify panel (dedicated flow) ────────────────────────────────────────────
const SHOPIFY_SCOPES = [
  { key: "sync_products", label: "Products & SKUs" },
  { key: "sync_inventory", label: "Inventory" },
  { key: "sync_orders", label: "Orders → sales" },
] as const;
type ShopifyScopeKey = (typeof SHOPIFY_SCOPES)[number]["key"];

function ShopifyPanel({ defaultIndustry, onDone }: { defaultIndustry: IndustryCode; onDone: () => void }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["integration", "shopify"],
    queryFn: integrationsApi.shopifyStatus,
    refetchInterval: (q) =>
      (q.state.data as IntegrationStatus | undefined)?.status === "syncing" ? 4000 : false,
  });
  const [shopDomain, setShopDomain] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [industry, setIndustry] = useState<IndustryCode>(defaultIndustry);
  const [scope, setScope] = useState<Record<ShopifyScopeKey, boolean>>({
    sync_products: true,
    sync_inventory: true,
    sync_orders: true,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["integration", "shopify"] });
    qc.invalidateQueries({ queryKey: ["integration", "catalog"] });
    onDone();
  };

  const connect = useMutation({
    mutationFn: () =>
      integrationsApi.shopifyConnect({
        shop_domain: shopDomain.trim(),
        access_token: accessToken.trim(),
        target_industry: industry,
        ...scope,
      }),
    onSuccess: (s) => {
      qc.setQueryData(["integration", "shopify"], s);
      setAccessToken("");
      toast.success(`Connected to ${s.shop_name ?? s.shop_domain}`);
      refresh();
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Could not connect to Shopify")),
  });
  const sync = useMutation({
    mutationFn: () => integrationsApi.shopifySync(scope),
    onSuccess: () => {
      toast.success("Sync started — this can take a minute");
      qc.invalidateQueries({ queryKey: ["integration", "shopify"] });
    },
  });
  const disconnect = useMutation({
    mutationFn: integrationsApi.shopifyDisconnect,
    onSuccess: (s) => {
      qc.setQueryData(["integration", "shopify"], s);
      toast.success("Shopify disconnected");
      refresh();
    },
  });

  if (isLoading || !data) return <div className="py-8 flex justify-center"><RefreshCw className="animate-spin text-content-subtle" /></div>;

  if (data.connected) {
    const isSyncing = data.status === "syncing";
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Meta label="Store" value={data.shop_name ?? data.shop_domain ?? "—"} />
          <Meta label="Industry" value={data.target_industry ?? "—"} />
          <Meta label="Last sync" value={data.last_sync_at ? fmtRelative(data.last_sync_at) : "Never"} />
          <Meta label="Result" value={data.last_sync_status ?? "—"} />
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" icon={<RefreshCw size={15} className={isSyncing ? "animate-spin" : ""} />} loading={sync.isPending} disabled={isSyncing} onClick={() => sync.mutate()}>
            {isSyncing ? "Syncing…" : "Sync now"}
          </Button>
          <Button variant="ghost" icon={<Unlink size={15} />} loading={disconnect.isPending} onClick={() => disconnect.mutate()}>
            Disconnect
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Input label="Store domain" name="shop_domain" placeholder="my-store.myshopify.com" value={shopDomain} onChange={(e) => setShopDomain(e.target.value)} />
      <IndustrySelect value={industry} onChange={setIndustry} />
      <Input
        label="Admin API access token"
        name="access_token"
        type="password"
        placeholder="shpat_••••"
        value={accessToken}
        onChange={(e) => setAccessToken(e.target.value)}
        hint="Shopify admin → Settings → Apps → Develop apps → Admin API access token"
      />
      <div>
        <label className="label">What to sync</label>
        <div className="grid grid-cols-3 gap-2">
          {SHOPIFY_SCOPES.map((f) => (
            <label key={f.key} className="flex items-center gap-2 p-2 rounded-lg border border-line cursor-pointer hover:bg-surface-2 text-xs">
              <input type="checkbox" checked={scope[f.key]} onChange={(e) => setScope((s) => ({ ...s, [f.key]: e.target.checked }))} className="accent-violet-600" />
              {f.label}
            </label>
          ))}
        </div>
      </div>
      <Button variant="primary" icon={<Link2 size={15} />} loading={connect.isPending} disabled={!shopDomain.trim() || accessToken.trim().length < 10} onClick={() => connect.mutate()} className="w-full justify-center">
        Connect Shopify
      </Button>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 rounded-xl bg-surface-2 border border-line">
      <div className="text-[10px] font-bold uppercase tracking-wider text-content-subtle">{label}</div>
      <div className="text-sm font-bold text-content mt-0.5 truncate capitalize">{value}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export const IntegrationsPage = () => {
  const qc = useQueryClient();
  const activeIndustry = useIndustryStore((s) => s.activeIndustry);
  const [selected, setSelected] = useState<Connector | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["integration", "catalog"],
    queryFn: integrationsApi.catalog,
  });

  const closeAndRefresh = () => {
    qc.invalidateQueries({ queryKey: ["integration", "catalog"] });
  };

  const disconnect = useMutation({
    mutationFn: (key: string) =>
      key === "shopify" ? integrationsApi.shopifyDisconnect().then(() => undefined) : integrationsApi.disconnect(key).then(() => undefined),
    onSuccess: () => {
      toast.success("Disconnected");
      closeAndRefresh();
      setSelected(null);
    },
  });

  const sync = useMutation({
    mutationFn: (key: string) => integrationsApi.sync(key),
    onSuccess: () => {
      toast.success("Sync started — this can take a minute");
      closeAndRefresh();
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Could not start sync")),
  });

  const isFile = selected?.key === "csv_upload" || selected?.key === "excel_upload";
  const isPush = selected?.key === "rest_api" || selected?.key === "webhooks";
  const isShopify = selected?.key === "shopify";

  const headerStats = useMemo(
    () => ({ total: data?.total ?? 0, live: data?.live ?? 0, connected: data?.connected ?? 0 }),
    [data],
  );

  if (isLoading || !data) return <PageLoader />;

  return (
    <div className="space-y-7 animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-content">Integrations Hub</h1>
          <p className="text-sm text-content-muted mt-1">
            Connect any data source — files, e-commerce, ERP, POS, warehouses or streams. Everything
            normalizes into SANKET's canonical schema before forecasting.
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant="primary">{headerStats.total} sources</Badge>
          <Badge variant="success" dot>{headerStats.live} live</Badge>
          {headerStats.connected > 0 && <Badge variant="info" dot>{headerStats.connected} connected</Badge>}
        </div>
      </div>

      {data.groups.map((grp) => (
        <div key={grp.category}>
          <h2 className="text-xs font-bold uppercase tracking-wider text-content-subtle mb-3">{grp.label}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {grp.connectors.map((c) => (
              <ConnectorCard key={c.key} c={c} onOpen={setSelected} />
            ))}
          </div>
        </div>
      ))}

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.name}
        size={isPush ? "lg" : "md"}
      >
        {selected && (
          <div className="space-y-4">
            <p className="text-sm text-content-muted -mt-1">{selected.summary}</p>

            {selected.error_message && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-50/70 border border-rose-200/70 dark:bg-rose-900/15 dark:border-rose-800/40 text-rose-700 dark:text-rose-300 text-sm">
                <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                <span>{selected.error_message}</span>
              </div>
            )}

            {selected.connected && !isFile && !isShopify && (
              <div className="flex flex-col gap-3 p-3 rounded-xl bg-emerald-50/60 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-emerald-700 dark:text-emerald-300 inline-flex items-center gap-1.5">
                    <CheckCircle2 size={15} /> Connected
                  </span>
                  <Button variant="ghost" size="sm" icon={<Unlink size={13} />} loading={disconnect.isPending} onClick={() => disconnect.mutate(selected.key)}>
                    Disconnect
                  </Button>
                </div>
                {selected.supports_sync && (
                  <div className="flex items-center gap-2 pt-2 border-t border-emerald-200/50 dark:border-emerald-500/20">
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<RefreshCw size={13} className={selected.status === "syncing" ? "animate-spin" : ""} />}
                      loading={sync.isPending}
                      disabled={selected.status === "syncing"}
                      onClick={() => sync.mutate(selected.key)}
                    >
                      {selected.status === "syncing" ? "Syncing…" : "Sync now"}
                    </Button>
                    {selected.last_sync_at && (
                      <span className="text-[10px] text-content-subtle">
                        Last sync: {fmtRelative(selected.last_sync_at)}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}

            {selected.status === "requested" && (
              <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-cyan-50/60 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/30">
                <span className="text-sm font-medium text-cyan-700 dark:text-cyan-300 inline-flex items-center gap-1.5">
                  <Clock size={15} /> Request submitted
                </span>
                <Button variant="ghost" size="sm" icon={<Unlink size={13} />} loading={disconnect.isPending} onClick={() => disconnect.mutate(selected.key)}>
                  Cancel
                </Button>
              </div>
            )}

            {isFile ? (
              <UploadPanel defaultIndustry={activeIndustry} onDone={closeAndRefresh} />
            ) : isShopify ? (
              <ShopifyPanel defaultIndustry={activeIndustry} onDone={() => { closeAndRefresh(); }} />
            ) : isPush ? (
              <PushPanel connector={selected} defaultIndustry={activeIndustry} onDone={closeAndRefresh} />
            ) : (
              <CredentialPanel connector={selected} defaultIndustry={activeIndustry} onDone={() => { closeAndRefresh(); setSelected(null); }} />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
