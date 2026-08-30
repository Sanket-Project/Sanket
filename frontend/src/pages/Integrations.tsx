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
  Search,
  Unlink,
  Upload,
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
import { useIndustryStore } from "@/stores/industry";
import { fmtRelative } from "@/utils/format";
import { getErrorMessage } from "@/utils/errors";
import type { IndustryCode } from "@/types/api";

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

function UploadPanel({ defaultIndustry, onDone }: { defaultIndustry: IndustryCode; onDone: () => void }) {
  const [kind, setKind] = useState<(typeof UPLOAD_KINDS)[number]["key"]>("sales");
  const [industry, setIndustry] = useState<IndustryCode>(defaultIndustry);
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Analysis states
  const [headers, setHeaders] = useState<string[] | null>(null);
  const [sampleRows, setSampleRows] = useState<Record<string, any>[] | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  const analyzeMutation = useMutation({
    mutationFn: (f: File) => integrationsApi.analyze(f, kind),
    onSuccess: (data) => {
      setHeaders(data.headers);
      setSampleRows(data.sample_rows);
      setMapping(data.suggested_mapping || {});
    },
    onError: (e) => {
      toast.error(getErrorMessage(e, "Failed to analyze file structure"));
      setFile(null);
    }
  });

  const upload = useMutation({
    mutationFn: () => integrationsApi.upload(file as File, kind, industry, mapping),
    onSuccess: (r) => {
      toast.success(`Imported ${r.rows_imported} of ${r.rows_total} rows`);
      onDone();
    },
    onError: (e: unknown) =>
      toast.error(getErrorMessage(e, "Upload failed")),
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] ?? null;
    setFile(selectedFile);
    if (selectedFile) {
      analyzeMutation.mutate(selectedFile);
    } else {
      setHeaders(null);
      setSampleRows(null);
      setMapping({});
    }
  };

  const resetFile = () => {
    setFile(null);
    setHeaders(null);
    setSampleRows(null);
    setMapping({});
    if (fileRef.current) fileRef.current.value = "";
  };

  const fields = useMemo(() => {
    if (kind === "sales") {
      return [
        { key: "sku", label: "SKU / Item Code", required: false, description: "Unique identifier for the product SKU" },
        { key: "name", label: "Product Name", required: false, description: "Product title/name (used to derive SKU if SKU code is missing)" },
        { key: "quantity", label: "Quantity", required: true, description: "Number of units sold" },
        { key: "timestamp", label: "Timestamp / Date", required: true, description: "Date and time of the sale" },
        { key: "price", label: "Unit Price", required: false, description: "Selling price per single unit" },
        { key: "revenue", label: "Gross Revenue", required: false, description: "Total line revenue (quantity * price if unmapped)" },
        { key: "discount", label: "Discount", required: false, description: "Total discount applied on the line" },
        { key: "channel", label: "Sales Channel", required: false, description: "e.g. POS, Online, Retail" },
        { key: "region", label: "Region / Market", required: false, description: "Store region or country" },
        { key: "order_id", label: "Order ID", required: false, description: "Invoice/transaction number" },
      ];
    }
    if (kind === "inventory") {
      return [
        { key: "sku", label: "SKU Code", required: true, description: "Product SKU to update inventory for" },
        { key: "available", label: "Available Stock", required: true, description: "Units currently on-hand/available" },
        { key: "reserved", label: "Reserved Stock", required: false, description: "Units allocated/reserved for orders" },
        { key: "inbound", label: "Inbound Stock", required: false, description: "Incoming stock from purchase orders" },
        { key: "warehouse", label: "Warehouse / Location", required: false, description: "WMS warehouse identifier" },
      ];
    }
    return [
      { key: "sku", label: "SKU Code", required: false, description: "Product SKU code" },
      { key: "name", label: "Product Name", required: false, description: "Product name/title" },
      { key: "brand", label: "Brand / Vendor", required: false, description: "Manufacturer or supplier name" },
      { key: "category", label: "Category", required: false, description: "Product department/type" },
      { key: "description", label: "Description", required: false, description: "Variant options or description" },
      { key: "gtin", label: "Barcode / GTIN", required: false, description: "UPC, EAN or GTIN" },
      { key: "price", label: "Unit Price / Cost", required: false, description: "Product base selling price" },
    ];
  }, [kind]);

  const validationError = useMemo(() => {
    if (!file || analyzeMutation.isPending) return null;
    const mappedKeys = Object.keys(mapping).filter((k) => mapping[k]);
    
    if (kind === "sales") {
      if (!mappedKeys.includes("sku") && !mappedKeys.includes("name")) {
        return "Either SKU or Product Name must be mapped to match records.";
      }
      if (!mappedKeys.includes("quantity")) return "Quantity column must be mapped.";
      if (!mappedKeys.includes("timestamp")) return "Date/Timestamp column must be mapped.";
    } else if (kind === "inventory") {
      if (!mappedKeys.includes("sku")) return "SKU column must be mapped.";
      if (!mappedKeys.includes("available")) return "Available Stock column must be mapped.";
    } else if (kind === "products") {
      if (!mappedKeys.includes("sku") && !mappedKeys.includes("name")) {
        return "Either SKU or Product Name must be mapped.";
      }
    }
    return null;
  }, [file, mapping, kind, analyzeMutation.isPending]);

  const updateMapping = (key: string, val: string) => {
    setMapping((prev) => ({
      ...prev,
      [key]: val,
    }));
  };

  const expected = UPLOAD_KINDS.find((k) => k.key === kind)!.cols;

  return (
    <div className="space-y-4">
      {!file && (
        <>
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
              onChange={handleFileChange}
              className="hidden"
            />
            <button
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-xl border border-dashed border-line hover:border-[var(--accent)]/50 bg-surface-2 px-4 py-6 flex flex-col items-center gap-2 text-content-muted transition-colors"
            >
              <Upload size={22} />
              <span className="text-sm font-medium">Click to choose a file</span>
              <span className="text-[11px] text-content-subtle">Expected columns: {expected}</span>
            </button>
          </div>

          <div className="rounded-xl bg-surface-2 border border-line p-3 text-[11px] text-content-subtle leading-relaxed">
            Columns are auto-mapped — common header names like "qty", "units", "price" and "date" are
            recognized. Unmatched or invalid rows are skipped and reported.
          </div>
        </>
      )}

      {file && analyzeMutation.isPending && (
        <div className="py-12 flex flex-col items-center gap-3 text-content-muted animate-pulse">
          <RefreshCw size={24} className="animate-spin text-[var(--accent)]" />
          <span className="text-sm font-medium">Analyzing file structure...</span>
        </div>
      )}

      {file && analyzeMutation.isSuccess && headers && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between p-3 rounded-xl bg-surface-2 border border-line">
            <div className="flex flex-col gap-0.5">
              <span className="text-xs font-bold text-content truncate max-w-[280px]">{file.name}</span>
              <span className="text-[10px] text-content-subtle font-mono uppercase">
                {(file.size / 1024).toFixed(1)} KB · {kind} feed
              </span>
            </div>
            <Button variant="ghost" size="sm" onClick={resetFile} className="text-rose-500 hover:text-rose-600">
              Change File
            </Button>
          </div>

          {sampleRows && sampleRows.length > 0 && (
            <div className="rounded-xl border border-line bg-surface-3 overflow-hidden shadow-inner">
              <div className="px-3 py-2 border-b border-line bg-surface-2 text-[10px] font-bold uppercase tracking-wider text-content-subtle">
                Data Preview (First {sampleRows.length} rows)
              </div>
              <div className="overflow-x-auto max-h-[140px] text-xs">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-line bg-surface-2/50">
                      {headers.map((h) => (
                        <th key={h} className="px-3 py-2 font-semibold text-content-muted whitespace-nowrap border-r border-line last:border-r-0">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sampleRows.map((row, idx) => (
                      <tr key={idx} className="border-b border-line last:border-b-0 hover:bg-surface-2/20">
                        {headers.map((h) => (
                          <td key={h} className="px-3 py-1.5 text-content-subtle font-mono border-r border-line last:border-r-0 max-w-[150px] truncate">
                            {row[h] !== null ? String(row[h]) : <span className="italic text-content-subtle/40">null</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-line p-4 bg-surface-2/40 space-y-3.5 shadow-sm">
            <h3 className="text-xs font-bold uppercase tracking-wider text-content-muted">
              Configure Column Mapping
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3">
              {fields.map((f) => (
                <div key={f.key} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-xs font-semibold text-content">
                    <span className="inline-flex items-center gap-1">
                      {f.label}
                      {f.required ? (
                        <span className="text-[9px] bg-rose-500/10 text-rose-500 font-bold px-1.5 py-0.2 rounded-full uppercase">
                          Required
                        </span>
                      ) : (
                        <span className="text-[9px] bg-slate-500/10 text-content-subtle font-bold px-1.5 py-0.2 rounded-full uppercase">
                          Optional
                        </span>
                      )}
                    </span>
                  </div>
                  <select
                    className="input py-1.5 text-xs h-9 bg-surface border-line"
                    value={mapping[f.key] ?? ""}
                    onChange={(e) => updateMapping(f.key, e.target.value)}
                  >
                    <option value="">— Skip / Default —</option>
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
            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-amber-50/70 border border-amber-200 text-amber-800 dark:bg-amber-900/10 dark:border-amber-900/30 dark:text-amber-400 text-xs">
              <AlertTriangle size={15} className="shrink-0 mt-0.5" />
              <span>{validationError}</span>
            </div>
          )}

          <Button
            variant="primary"
            icon={<Upload size={15} />}
            loading={upload.isPending}
            disabled={!!validationError}
            onClick={() => upload.mutate()}
            className="w-full justify-center mt-2"
          >
            Confirm & Import Data
          </Button>
        </div>
      )}
    </div>
  );}

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

  const priorityConnectors = useMemo(() => data?.groups
    .flatMap((group) => group.connectors)
    .filter((connector) => connector.connected || connector.status === "error" || connector.status === "requested") ?? [], [data]);

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

      {priorityConnectors.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div><h2 className="text-sm font-semibold text-content">Connections needing your attention</h2><p className="mt-0.5 text-xs text-content-muted">Connected, syncing, requested, and failed sources appear before the full catalogue.</p></div>
            <Badge variant={priorityConnectors.some((connector) => connector.status === "error") ? "danger" : "success"}>{priorityConnectors.length}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {priorityConnectors.map((connector) => <ConnectorCard key={`priority-${connector.key}`} c={connector} onOpen={setSelected} />)}
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
