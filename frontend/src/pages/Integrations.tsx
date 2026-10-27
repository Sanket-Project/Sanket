import { useMemo, useState } from "react";
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
  Search,
  Unlink,
  Warehouse,
  Webhook,
  type AppIcon,
} from "@/components/ui/icons";
import toast from "react-hot-toast";
import clsx from "clsx";
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
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { fmtRelative } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import { connectionGroups } from "@/utils/integrationGroups";
import { ImportUploader } from "@/components/integrations/ImportUploader";

const ICONS: Record<string, AppIcon> = {
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

const FEED_ICONS: Record<string, AppIcon> = {
  sales: Receipt,
  inventory: Boxes,
  products: Package,
  warehouse: Warehouse,
  purchase_orders: Receipt,
};

// Official brand marks where available. Simple Icons serves the vendor-owned
// marks; Indian ERP products without a Simple Icons entry use the favicon from
// their official domain so the catalog never pretends a generic glyph is the
// brand's logo.
const connectorAsset = (name: string) => `${import.meta.env.BASE_URL}assets/connectors/${name}.svg`;

const OFFICIAL_LOGOS: Record<string, string> = {
  shopify: connectorAsset("shopify"),
  woocommerce: connectorAsset("woocommerce"),
  magento: "https://www.google.com/s2/favicons?domain=business.adobe.com&sz=128",
  bigcommerce: connectorAsset("bigcommerce"),
  amazon: "https://www.google.com/s2/favicons?domain=sellercentral.amazon.in&sz=128",
  square: connectorAsset("square"),
  sap: connectorAsset("sap"),
  netsuite: "https://www.google.com/s2/favicons?domain=oracle.com&sz=128",
  odoo: connectorAsset("odoo"),
  tally_prime: "https://www.google.com/s2/favicons?domain=tallysolutions.com&sz=128",
  zoho_books: "https://www.google.com/s2/favicons?domain=zoho.com&sz=128",
  zoho_inventory: "https://www.google.com/s2/favicons?domain=zoho.com&sz=128",
  busy_accounting: "https://www.google.com/s2/favicons?domain=busy.in&sz=128",
  marg_erp: "https://www.google.com/s2/favicons?domain=margcompusoft.com&sz=128",
  vyapar: "https://www.google.com/s2/favicons?domain=vyaparapp.in&sz=128",
  erpnext: connectorAsset("erpnext"),
  unicommerce: "https://www.google.com/s2/favicons?domain=unicommerce.com&sz=128",
  stripe: connectorAsset("stripe"),
  quickbooks: connectorAsset("quickbooks"),
  xero: connectorAsset("xero"),
};

function ConnectorLogo({ connector }: { connector: Connector }) {
  const [failed, setFailed] = useState(false);
  const Icon = ICONS[connector.icon] ?? Plug;
  const logo = OFFICIAL_LOGOS[connector.key];

  return (
    <div className="brand-logo-tile grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-line bg-white p-2 shadow-sm">
      {logo && !failed ? (
        <img src={logo} alt={`${connector.name} logo`} className="h-full w-full object-contain" onError={() => setFailed(true)} />
      ) : (
        <Icon size={21} className="text-content-muted" aria-hidden="true" />
      )}
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
  return (
    <button
      onClick={() => onOpen(c)}
      className="text-left group rounded-2xl border border-line bg-surface hover:border-[var(--accent)]/40 hover:shadow-md transition-all p-4 flex flex-col gap-3"
    >
      <div className="flex items-start justify-between gap-2">
        <ConnectorLogo connector={c} />
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

export function UploadPanel({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"sales" | "inventory" | "products">("sales");
  return <div className="space-y-4">
    <fieldset className="flex flex-wrap gap-2"><legend className="label">What are you importing?</legend>
      {UPLOAD_KINDS.map((item) => <button key={item.key} type="button" aria-pressed={kind === item.key}
        className="rounded-xl border border-line px-3 py-2 text-sm" onClick={() => setKind(item.key)}>{item.label}</button>)}
    </fieldset>
    <ImportUploader key={kind} kind={kind} mode="integrations" onImported={() => {
      void queryClient.invalidateQueries();
      onDone();
    }} />
  </div>;
}

// ── Generic credential / request panel ────────────────────────────────────────
function CredentialPanel({ connector, onDone }: { connector: Connector; onDone: () => void }) {
  const [creds, setCreds] = useState<Record<string, string>>({});
  const isPlanned = connector.availability === "planned";

  const connect = useMutation({
    mutationFn: () => integrationsApi.connect(connector.key, { credentials: creds }),
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
function PushPanel({ connector, onDone }: { connector: Connector; onDone: () => void }) {
  const [token, setToken] = useState<string | null>(null);
  const endpoint = `${window.location.origin}/api/v1/integrations/ingest`;

  const connect = useMutation({
    mutationFn: () => integrationsApi.connect(connector.key, { credentials: {} }),
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

function ShopifyPanel({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["integration", "shopify"],
    queryFn: integrationsApi.shopifyStatus,
    refetchInterval: (q) =>
      (q.state.data as IntegrationStatus | undefined)?.status === "syncing" ? 4000 : false,
  });
  // Synced data lands in the workspace's own industry — the server decides it,
  // this is only the label.
  const workspaceIndustry = useWorkspaceIndustry();
  const [shopDomain, setShopDomain] = useState("");
  const [accessToken, setAccessToken] = useState("");
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
          <Meta label="Industry" value={industryDisplay[workspaceIndustry]} />
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
  const [selected, setSelected] = useState<Connector | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "connected" | "attention" | "available">("all");

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

  const filteredGroups = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLowerCase();
    return data.groups
      .filter((group) => category === "all" || group.category === category)
      .map((group) => ({
        ...group,
        connectors: group.connectors
          .filter((connector) => {
            const matchesSearch = !query || `${connector.name} ${connector.summary} ${connector.feeds.join(" ")}`.toLowerCase().includes(query);
            const needsAttention = connector.status === "error" || connector.status === "requested";
            const matchesStatus = statusFilter === "all"
              || (statusFilter === "connected" && connector.connected)
              || (statusFilter === "attention" && needsAttention)
              || (statusFilter === "available" && connector.availability !== "planned");
            return matchesSearch && matchesStatus;
          })
          .sort((a, b) => {
            const priority = (connector: Connector) => connector.status === "error" ? 0 : connector.connected ? 1 : connector.status === "requested" ? 2 : connector.availability === "live" ? 3 : 4;
            return priority(a) - priority(b) || a.name.localeCompare(b.name);
          }),
      }))
      .filter((group) => group.connectors.length > 0);
  }, [category, data, search, statusFilter]);

  const { attention, connected } = useMemo(
    () => connectionGroups(data?.groups.flatMap((group) => group.connectors) ?? []),
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

      {attention.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div><h2 className="text-sm font-semibold text-content">Needs attention</h2><p className="mt-0.5 text-xs text-content-muted">Failed syncs and connection requests that are waiting on you.</p></div>
            <Badge variant={attention.some((connector) => connector.status === "error") ? "danger" : "warning"}>{attention.length}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {attention.map((connector) => <ConnectorCard key={`attention-${connector.key}`} c={connector} onOpen={setSelected} />)}
          </div>
        </section>
      )}

      {connected.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div><h2 className="text-sm font-semibold text-content">Connected sources</h2><p className="mt-0.5 text-xs text-content-muted">Working connections. Open one to sync, upload or disconnect.</p></div>
            <Badge variant="success">{connected.length}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {connected.map((connector) => <ConnectorCard key={`connected-${connector.key}`} c={connector} onOpen={setSelected} />)}
          </div>
        </section>
      )}

      <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-3 sm:flex-row sm:items-center">
        <label className="relative min-w-0 flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-subtle" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search Tally, Shopify, inventory…" aria-label="Search integrations" className="input h-10 w-full pl-9" />
        </label>
        <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter integration category" className="input h-10 min-w-44 sm:w-auto">
          <option value="all">All categories</option>
          {data.groups.map((group) => <option key={group.category} value={group.category}>{group.label}</option>)}
        </select>
        <div className="flex flex-wrap gap-1 rounded-xl bg-surface-2 p-1" aria-label="Filter integrations by status">
          {(["all", "available", "connected", "attention"] as const).map((filter) => (
            <button key={filter} onClick={() => setStatusFilter(filter)} className={clsx("rounded-lg px-3 py-2 text-xs font-semibold capitalize transition", statusFilter === filter ? "bg-surface text-content shadow-sm" : "text-content-muted hover:text-content")}>{filter}</button>
          ))}
        </div>
      </div>

      {filteredGroups.map((grp) => (
        <div key={grp.category}>
          <h2 className="text-xs font-bold uppercase tracking-wider text-content-subtle mb-3">{grp.label}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {grp.connectors.map((c) => (
              <ConnectorCard key={c.key} c={c} onOpen={setSelected} />
            ))}
          </div>
        </div>
      ))}
      {filteredGroups.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center"><Search size={22} className="mx-auto text-content-subtle" /><p className="mt-3 text-sm font-semibold text-content">No connectors match these filters</p><button onClick={() => { setSearch(""); setCategory("all"); setStatusFilter("all"); }} className="mt-2 text-xs font-semibold text-[var(--accent)]">Clear filters</button></div>
      )}

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.name}
        size={isPush || isFile ? "lg" : "md"}
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
              <UploadPanel onDone={closeAndRefresh} />
            ) : isShopify ? (
              <ShopifyPanel onDone={() => { closeAndRefresh(); }} />
            ) : isPush ? (
              <PushPanel connector={selected} onDone={closeAndRefresh} />
            ) : (
              <CredentialPanel connector={selected} onDone={() => { closeAndRefresh(); setSelected(null); }} />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
