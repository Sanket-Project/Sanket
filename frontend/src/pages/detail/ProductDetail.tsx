import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Camera,
  Trash2,
  Tag,
  Layers,
  ChevronRight,
  Package,
  CheckCircle2,
  Clock,
  Star,
  XCircle,
  ExternalLink,
  Sprout,
  Cpu,
  Shirt,
  Pill,
  Wrench,
  TrendingUp,
  ShieldCheck,
} from "lucide-react";
import clsx from "clsx";
import { productsApi } from "@/api/products";
import { skusApi } from "@/api/skus";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageLoader } from "@/components/ui/Spinner";
import { fmtDate, fmtNumber, fmtRelative } from "@/utils/format";
import type { Sku, ProductStatus, IndustryCode } from "@/types/api";
import { useProductImagesStore, getProductImage } from "@/stores/productImages";
import toast from "react-hot-toast";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { getErrorMessage } from "@/utils/errors";
import { industryAccent, industryGradient, industryDisplay } from "@/utils/colors";

// ─────────────────────────────────────────────────────────────────────────────
// Status config
// ─────────────────────────────────────────────────────────────────────────────
const STATUS_CONFIG: Record<ProductStatus, { label: string; cls: string; icon: React.ReactNode }> = {
  active: { label: "Active", cls: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800/40", icon: <CheckCircle2 size={12} /> },
  seasonal: { label: "Seasonal", cls: "text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20 border-sky-200 dark:border-sky-800/40", icon: <Clock size={12} /> },
  clearance: { label: "Clearance", cls: "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/40", icon: <Tag size={12} /> },
  pre_launch: { label: "Pre-Launch", cls: "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-800/40", icon: <Star size={12} /> },
  discontinued: { label: "Discontinued", cls: "text-rose-500 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800/40", icon: <XCircle size={12} /> },
};

const INDUSTRY_ICONS: Record<IndustryCode, React.ReactNode> = {
  agrocenter: <Sprout size={14} />,
  electronics: <Cpu size={14} />,
  fashion: <Shirt size={14} />,
  pharma: <Pill size={14} />,
  hardware: <Wrench size={14} />,
};

// ─────────────────────────────────────────────────────────────────────────────
// SKU mini-card
// ─────────────────────────────────────────────────────────────────────────────
function SkuMiniCard({ sku, gradient, onClick }: {
  sku: Sku;
  gradient: string;
  onClick: () => void;
}) {
  const { formatPrice } = useFormattedCurrency();
  const price = sku.unit_price != null ? Number(sku.unit_price) : null;
  const cost = sku.unit_cost != null ? Number(sku.unit_cost) : null;
  const margin = price && cost && price > 0 ? ((price - cost) / price) * 100 : null;

  return (
    <button
      onClick={onClick}
      className="w-full text-left glass rounded-xl overflow-hidden group card-hover-premium cursor-pointer"
    >
      <div className="h-0.5 w-full" style={{ background: gradient }} />
      <div className="p-3.5">
        <div className="flex items-start justify-between gap-2 mb-2">
          <span className="font-mono text-[10px] font-bold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40">
            {sku.sku_code}
          </span>
          {sku.is_active ? (
            <span className="flex items-center gap-1 text-[8px] font-bold text-emerald-600 dark:text-emerald-400">
              <span className="h-1 w-1 rounded-full bg-emerald-500 animate-pulse" /> Active
            </span>
          ) : (
            <span className="text-[8px] font-bold text-slate-400 dark:text-slate-500">Inactive</span>
          )}
        </div>

        <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 leading-snug mb-2.5 line-clamp-2">
          {sku.description ?? sku.sku_code}
        </p>

        <div className="grid grid-cols-3 gap-1.5 mb-2.5">
          <div className="text-center bg-slate-50 dark:bg-slate-800/40 rounded-lg p-1.5">
            <div className="text-xs font-bold text-slate-800 dark:text-slate-100">
              {price != null ? formatPrice(price) : "—"}
            </div>
            <div className="text-[8px] text-slate-400 dark:text-slate-500">price</div>
          </div>
          <div className="text-center bg-slate-50 dark:bg-slate-800/40 rounded-lg p-1.5">
            <div className={clsx("text-xs font-bold", margin != null ? (margin >= 40 ? "text-emerald-600 dark:text-emerald-400" : margin >= 20 ? "text-amber-600 dark:text-amber-400" : "text-rose-500") : "text-slate-400")}>
              {margin != null ? `${margin.toFixed(0)}%` : "—"}
            </div>
            <div className="text-[8px] text-slate-400 dark:text-slate-500">margin</div>
          </div>
          <div className="text-center bg-slate-50 dark:bg-slate-800/40 rounded-lg p-1.5">
            <div className={clsx("text-xs font-bold", (sku.lead_time_days ?? 0) > 45 ? "text-rose-500" : (sku.lead_time_days ?? 0) > 25 ? "text-amber-600" : "text-emerald-600")}>
              {sku.lead_time_days != null ? `${sku.lead_time_days}d` : "—"}
            </div>
            <div className="text-[8px] text-slate-400 dark:text-slate-500">lead</div>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-slate-400 dark:text-slate-500">
              Safety: <strong className="text-slate-600 dark:text-slate-300">{fmtNumber(sku.safety_stock)}</strong>
            </span>
          </div>
          <ChevronRight size={12} className="text-slate-300 dark:text-slate-600 group-hover:text-slate-500 dark:group-hover:text-slate-400 transition-colors" style={{ color: undefined }} />
        </div>
      </div>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
export const ProductDetailPage = () => {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: product, isLoading } = useQuery({
    queryKey: ["product", id],
    queryFn: () => productsApi.get(id),
    enabled: !!id,
  });

  const remove = useMutation({
    mutationFn: () => productsApi.remove(id),
    onSuccess: (res) => {
      toast.success(
        res.cascaded_skus > 0
          ? `Product and ${res.cascaded_skus} SKU${res.cascaded_skus !== 1 ? "s" : ""} deleted`
          : "Product deleted",
      );
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["skus"] });
      navigate("/workspace/products");
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, "Could not delete this product"));
      setConfirmDelete(false);
    },
  });

  const { data: allSkus } = useQuery({
    queryKey: ["skus", "list"],
    queryFn: () => skusApi.list({ limit: 500, active_only: false }),
  });

  const { images, uploadImage, removeImage } = useProductImagesStore();

  if (isLoading || !product) return <PageLoader />;

  const imgUrl = getProductImage(product.id, product.industry, images);
  const skus = (allSkus ?? []).filter((s) => s.product_id === product.id);
  const accent = industryAccent[product.industry];
  const gradient = industryGradient[product.industry];
  const displayName = industryDisplay[product.industry];
  const status = STATUS_CONFIG[product.status];
  const industryIcon = INDUSTRY_ICONS[product.industry];

  // SKU aggregate stats
  const activeSkus = skus.filter((s) => s.is_active).length;
  const skusWithCost = skus.filter(
    (s) => s.unit_price != null && s.unit_cost != null && Number(s.unit_price) > 0,
  );
  const avgMargin = skusWithCost.length
    ? skusWithCost.reduce(
        (sum, s) => sum + ((Number(s.unit_price) - Number(s.unit_cost)) / Number(s.unit_price)) * 100,
        0,
      ) / skusWithCost.length
    : null;
  const avgLeadTime = skus.filter((s) => s.lead_time_days != null).reduce((sum, s) => sum + (s.lead_time_days ?? 0), 0) / (skus.filter((s) => s.lead_time_days != null).length || 1);
  const skusWithSafety = skus.filter((s) => s.safety_stock != null);
  const totalSafetyStock = skusWithSafety.length
    ? skusWithSafety.reduce((sum, s) => sum + (s.safety_stock ?? 0), 0)
    : null;

  return (
    <div className="space-y-6 animate-fade-in">

      {/* ── Breadcrumb ── */}
      <div className="flex items-center justify-between">
        <Link
          to="/workspace/products"
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
        >
          <ArrowLeft size={14} /> Back to Products
        </Link>
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1 rounded-full"
            style={{ background: `${accent}15`, color: accent }}
          >
            {industryIcon} {displayName}
          </span>
          <span className={clsx("inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border", status.cls)}>
            {status.icon} {status.label}
          </span>
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 size={13} />}
            onClick={() => setConfirmDelete(true)}
            className="font-semibold"
          >
            Delete
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this product?"
        confirmLabel="Delete product"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onClose={() => setConfirmDelete(false)}
        message={
          <>
            <p>
              Permanently delete <strong>{product.name}</strong>?
              {skus.length > 0 && (
                <>
                  {" "}
                  This also deletes its{" "}
                  <strong>
                    {skus.length} linked SKU{skus.length !== 1 ? "s" : ""}
                  </strong>
                  .
                </>
              )}
            </p>
            <p className="mt-2 text-xs text-slate-400">This action cannot be undone.</p>
          </>
        }
      />

      {/* ── Hero card ── */}
      <div className="glass rounded-2xl overflow-hidden">
        <div className="h-1.5 w-full" style={{ background: gradient }} />

        <div className="p-6">
          <div className="flex flex-col md:flex-row gap-6 items-start">
            {/* Product image */}
            <div className="relative h-40 w-40 rounded-2xl overflow-hidden bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-800/60 dark:to-slate-700/40 border border-slate-200/60 dark:border-slate-700/40 shadow-md group shrink-0">
              <img
                src={imgUrl}
                alt={product.name}
                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              />
              <label className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer select-none text-center p-2">
                <Camera size={18} className="mb-1 text-violet-300" />
                <span className="text-[10px] font-bold tracking-wide uppercase">Change Photo</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onloadend = () => { uploadImage(product.id, reader.result as string); toast.success("Image updated!"); };
                      reader.readAsDataURL(file);
                    }
                  }}
                  className="hidden"
                />
              </label>
              {images[product.id] && (
                <button
                  type="button"
                  onClick={() => { removeImage(product.id); toast.success("Image removed"); }}
                  className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 hover:bg-rose-600/90 text-white transition border-none cursor-pointer flex items-center justify-center"
                >
                  <Trash2 size={11} />
                </button>
              )}
            </div>

            {/* Identity */}
            <div className="flex-1 min-w-0">
              {/* Brand */}
              {product.brand && (
                <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-1">{product.brand}</p>
              )}

              {/* Name */}
              <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight mb-1">
                {product.name}
              </h1>

              {/* Category breadcrumb */}
              <div className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400 mb-3">
                <Tag size={12} />
                <span>{product.category}</span>
                {product.subcategory && (
                  <>
                    <ChevronRight size={12} className="text-slate-300 dark:text-slate-600" />
                    <span>{product.subcategory}</span>
                  </>
                )}
              </div>

              {/* Badges */}
              <div className="flex flex-wrap items-center gap-2">
                {product.external_id && (
                  <span className="flex items-center gap-1 text-[10px] font-semibold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 px-2 py-0.5 rounded">
                    <Tag size={9} /> {product.external_id}
                  </span>
                )}
              </div>

              {/* Dates */}
              <div className="flex flex-wrap gap-4 text-[11px] text-slate-400 dark:text-slate-500 mt-3">
                <span>Created <strong className="text-slate-600 dark:text-slate-300">{fmtDate(product.created_at)}</strong></span>
                <span>Updated <strong className="text-slate-600 dark:text-slate-300">{fmtDate(product.updated_at)}</strong> · {fmtRelative(product.updated_at)}</span>
                <span className="font-mono text-[10px] bg-slate-100 dark:bg-slate-800/60 px-2 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40">{product.id.slice(0, 20)}…</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── SKU Summary stats (only shown if SKUs exist) ── */}
      {skus.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Total SKUs", value: skus.length.toString(), sub: `${activeSkus} active`, icon: <Layers size={14} />, tone: "default" },
            { label: "Avg. Margin", value: avgMargin != null ? `${avgMargin.toFixed(1)}%` : "—", sub: "Price − Cost / Price", icon: <TrendingUp size={14} />, tone: avgMargin == null ? "default" : avgMargin >= 40 ? "up" : avgMargin >= 20 ? "warn" : "down" },
            { label: "Avg. Lead Time", value: avgLeadTime > 0 ? `${Math.round(avgLeadTime)}d` : "—", sub: "Days to replenish", icon: <Clock size={14} />, tone: avgLeadTime > 45 ? "down" : avgLeadTime > 25 ? "warn" : "up" },
            { label: "Total Safety Stock", value: fmtNumber(totalSafetyStock), sub: "Units across all SKUs", icon: <ShieldCheck size={14} />, tone: "default" },
          ].map(({ label, value, sub, icon: ic, tone }) => (
            <div key={label} className="glass rounded-xl p-3.5">
              <div className={clsx(
                "h-7 w-7 rounded-lg flex items-center justify-center mb-2",
                tone === "up" ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400" :
                tone === "warn" ? "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400" :
                tone === "down" ? "bg-rose-50 dark:bg-rose-900/20 text-rose-500 dark:text-rose-400" :
                "bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400"
              )}>
                {ic}
              </div>
              <div className="text-xl font-black text-slate-900 dark:text-white">{value}</div>
              <div className="text-[9px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">{label}</div>
              <div className="text-[9px] text-slate-400 dark:text-slate-500">{sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── SKU Cards grid ── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Layers size={14} className="text-slate-400 dark:text-slate-500" />
            <h2 className="text-sm font-bold text-slate-800 dark:text-slate-100">
              SKUs under this product
            </h2>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{ background: `${accent}15`, color: accent }}>
              {skus.length}
            </span>
          </div>
          <Button
            variant="secondary"
            size="sm"
            icon={<ExternalLink size={12} />}
            onClick={() => navigate("/workspace/skus")}
            className="text-xs glass border border-slate-200 dark:border-slate-700"
          >
            View all SKUs
          </Button>
        </div>

        {skus.length === 0 ? (
          <div className="glass rounded-2xl p-12 text-center">
            <Package size={28} className="mx-auto text-slate-300 dark:text-slate-600 mb-3" />
            <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No SKUs yet</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              Add SKUs to this product to enable forecasting and inventory tracking.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {skus.map((s) => (
              <SkuMiniCard
                key={s.id}
                sku={s}
                gradient={gradient}
                onClick={() => navigate(`/workspace/skus/${s.id}`)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Attributes ── */}
      {Object.keys(product.attributes).length > 0 && (
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Tag size={14} className="text-slate-400 dark:text-slate-500" />
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">Product Attributes</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
            {Object.entries(product.attributes).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-700/40">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 capitalize">{k.replace(/_/g, " ")}</span>
                <span className="text-xs font-bold text-slate-800 dark:text-slate-100 truncate max-w-[55%] text-right">
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
