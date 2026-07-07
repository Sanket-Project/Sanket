import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Search,
  Upload,
  Image as ImageIcon,
  FileSpreadsheet,
  Sprout,
  Cpu,
  Shirt,
  Pill,
  Wrench,
  ChevronRight,
  LayoutGrid,
  List,
  Filter,
  Package,
  Tag,
  CheckCircle2,
  Clock,
  XCircle,
  Star,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { productsApi, type ProductCreateBody } from "@/api/products";
import { skusApi } from "@/api/skus";
import { exportApi } from "@/api/export";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ImportModal } from "@/components/ui/ImportModal";
import { fmtRelative } from "@/utils/format";
import type { Product, ProductStatus, IndustryCode } from "@/types/api";
import { useProductImagesStore, getProductImage } from "@/stores/productImages";
import { useIndustryStore } from "@/stores/industry";
import { industryAccent, industryGradient, industryDisplay } from "@/utils/colors";
import {
  parseFile,
  validateProductRows,
  downloadProductTemplate,
  PRODUCT_REQUIRED_COLUMNS,
  PRODUCT_ALL_COLUMNS,
} from "@/utils/csvImport";

// ─────────────────────────────────────────────────────────────────────────────
// Industry config
// ─────────────────────────────────────────────────────────────────────────────
const INDUSTRY_ICONS: Record<IndustryCode, React.ReactNode> = {
  agrocenter: <Sprout size={16} />,
  electronics: <Cpu size={16} />,
  fashion: <Shirt size={16} />,
  pharma: <Pill size={16} />,
  hardware: <Wrench size={16} />,
};

const INDUSTRY_CATEGORY_HINTS: Record<IndustryCode, string[]> = {
  agrocenter: ["Fertilizers", "Seeds", "Pesticides", "Irrigation", "Soil Amendments"],
  electronics: ["Smartphones", "Laptops", "Audio", "Smart Home", "Tablets", "Accessories"],
  fashion: ["Women's Apparel", "Men's Apparel", "Footwear", "Accessories", "Bags"],
  pharma: ["Oncology", "Allergy", "Metabolic", "Antibiotics", "Cardiovascular"],
  hardware: ["Power Tools", "Fasteners", "Electrical", "Plumbing", "Building Materials", "Safety"],
};

// ─────────────────────────────────────────────────────────────────────────────
// Status config
// ─────────────────────────────────────────────────────────────────────────────
const STATUS_CONFIG: Record<ProductStatus, { label: string; cls: string; icon: React.ReactNode }> = {
  active: { label: "Active", cls: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800/40", icon: <CheckCircle2 size={10} /> },
  seasonal: { label: "Seasonal", cls: "text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20 border-sky-200 dark:border-sky-800/40", icon: <Clock size={10} /> },
  clearance: { label: "Clearance", cls: "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/40", icon: <Tag size={10} /> },
  pre_launch: { label: "Pre-Launch", cls: "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-800/40", icon: <Star size={10} /> },
  discontinued: { label: "Discontinued", cls: "text-rose-500 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800/40", icon: <XCircle size={10} /> },
};


// ─────────────────────────────────────────────────────────────────────────────
// Product Card (grid view)
// ─────────────────────────────────────────────────────────────────────────────
function ProductCard({ product, accent, gradient, images, skuCountMap, onClick }: {
  product: Product;
  accent: string;
  gradient: string;
  images: Record<string, string>;
  skuCountMap: Record<string, number>;
  onClick: () => void;
}) {
  const imgUrl = getProductImage(product.id, product.industry, images);
  const status = STATUS_CONFIG[product.status];
  const skuCount = skuCountMap[product.id] ?? 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left glass rounded-2xl overflow-hidden card-hover-premium group cursor-pointer"
    >
      {/* Accent bar */}
      <div className="h-1 w-full" style={{ background: gradient }} />

      {/* Product image banner */}
      <div className="relative h-36 bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-800/60 dark:to-slate-700/40 overflow-hidden">
        <img
          src={imgUrl}
          alt={product.name}
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105 opacity-90"
        />
        {/* Status badge on image */}
        <div className="absolute top-2.5 left-2.5">
          <span className={clsx("inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border", status.cls)}>
            {status.icon} {status.label}
          </span>
        </div>
        {/* SKU count badge */}
        {skuCount > 0 && (
          <div className="absolute top-2.5 right-2.5 bg-black/50 backdrop-blur-sm text-white text-[9px] font-bold px-2 py-0.5 rounded-full">
            {skuCount} SKU{skuCount !== 1 ? "s" : ""}
          </div>
        )}
      </div>

      <div className="p-4">
        {/* Brand + category */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          {product.brand && (
            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider truncate">{product.brand}</span>
          )}
          <span className="text-[9px] font-semibold text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800/60 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700/40 shrink-0 ml-auto">
            {product.category}
          </span>
        </div>

        {/* Product name */}
        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 leading-snug line-clamp-2 mb-1.5">
          {product.name}
        </h3>

        {/* Subcategory */}
        {product.subcategory && (
          <p className="text-[10px] text-slate-400 dark:text-slate-500 mb-3">{product.subcategory}</p>
        )}

        {/* External ID + updated */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-100/80 dark:border-slate-700/40">
          {product.external_id ? (
            <span className="font-mono text-[9px] text-slate-400 dark:text-slate-500">{product.external_id}</span>
          ) : (
            <span className="text-[9px] text-slate-300 dark:text-slate-600">—</span>
          )}
          <span className="text-[9px] text-slate-400 dark:text-slate-500">{fmtRelative(product.updated_at)}</span>
        </div>
      </div>

      {/* Hover arrow */}
      <div className="px-4 pb-3.5 flex items-center justify-end -mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="flex items-center gap-1 text-[10px] font-bold" style={{ color: accent }}>
          View details <ChevronRight size={11} />
        </span>
      </div>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Product Row (list view)
// ─────────────────────────────────────────────────────────────────────────────
function ProductRow({ product, gradient, images, skuCountMap, onClick }: {
  product: Product;
  gradient: string;
  images: Record<string, string>;
  skuCountMap: Record<string, number>;
  onClick: () => void;
}) {
  const imgUrl = getProductImage(product.id, product.industry, images);
  const status = STATUS_CONFIG[product.status];
  const skuCount = skuCountMap[product.id] ?? 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors group border border-transparent hover:border-slate-200/60 dark:hover:border-slate-700/40"
    >
      {/* Colour dot */}
      <div className="h-8 w-1 rounded-full shrink-0" style={{ background: gradient }} />

      {/* Image thumbnail */}
      <div className="h-10 w-10 rounded-xl overflow-hidden bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/40 shrink-0">
        <img src={imgUrl} alt={product.name} className="h-full w-full object-cover" />
      </div>

      {/* Name + brand + category */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{product.name}</p>
        </div>
        <p className="text-[10px] text-slate-400 dark:text-slate-500 truncate">
          {product.brand && <span className="font-semibold">{product.brand} · </span>}
          {product.category}{product.subcategory && ` › ${product.subcategory}`}
        </p>
      </div>

      {/* Status */}
      <span className={clsx("shrink-0 inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border hidden sm:inline-flex", status.cls)}>
        {status.icon} {status.label}
      </span>

      {/* SKU count */}
      <div className="text-right shrink-0 w-16 hidden md:block">
        <div className="text-sm font-bold text-slate-700 dark:text-slate-200">{skuCount}</div>
        <div className="text-[9px] text-slate-400 dark:text-slate-500">SKUs</div>
      </div>

      {/* Updated */}
      <div className="text-[10px] text-slate-400 dark:text-slate-500 shrink-0 w-24 text-right hidden lg:block">
        {fmtRelative(product.updated_at)}
      </div>

      <ChevronRight size={14} className="text-slate-300 dark:text-slate-600 group-hover:text-slate-500 dark:group-hover:text-slate-400 transition-colors shrink-0" />
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
type ViewMode = "grid" | "list";
type FilterStatus = "all" | ProductStatus;

export const ProductsPage = () => {
  const navigate = useNavigate();
  const industry = useIndustryStore((s) => s.activeIndustry);
  const accent = industryAccent[industry];
  const gradient = industryGradient[industry];
  const displayName = industryDisplay[industry];
  const icon = INDUSTRY_ICONS[industry];
  const categoryHints = INDUSTRY_CATEGORY_HINTS[industry];

  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [filterCategory, setFilterCategory] = useState("all");
  const [addProductOpen, setAddProductOpen] = useState(false);
  const [modalTab, setModalTab] = useState<"manual" | "import">("manual");
  const [uploadFile, setUploadFile] = useState<string | null>(null);
  const qc = useQueryClient();
  const { images, uploadImage } = useProductImagesStore();

  const { data: liveProducts } = useQuery({
    queryKey: ["products", "list"],
    queryFn: () => productsApi.list(100, 0),
    retry: 1,
  });

  const products: Product[] = liveProducts || [];

  const create = useMutation({
    mutationFn: (body: ProductCreateBody) => productsApi.create(body),
    onSuccess: (newProduct) => {
      toast.success("Product created");
      if (uploadFile && newProduct?.id) uploadImage(newProduct.id, uploadFile);
      qc.invalidateQueries({ queryKey: ["products"] });
      setAddProductOpen(false);
      setUploadFile(null);
    },
    onError: () => toast.error("Failed to create product"),
  });

  // Unique categories from current product list
  const categories = useMemo(() => {
    const cats = Array.from(new Set(products.map((p) => p.category)));
    return cats.sort();
  }, [products]);

  // Filtered + sorted products
  const filtered = useMemo(() => {
    let list = products;
    if (filterStatus !== "all") list = list.filter((p) => p.status === filterStatus);
    if (filterCategory !== "all") list = list.filter((p) => p.category === filterCategory);
    if (query) {
      const q = query.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.category.toLowerCase().includes(q) ||
          (p.brand ?? "").toLowerCase().includes(q) ||
          (p.external_id ?? "").toLowerCase().includes(q),
      );
    }
    return list;
  }, [products, query, filterStatus, filterCategory]);

  // Summary counts
  const activeCount = products.filter((p) => p.status === "active").length;
  const categories_count = new Set(products.map((p) => p.category)).size;
  const prelaunchCount = products.filter((p) => p.status === "pre_launch").length;

  // Real SKU counts per product, grouped from the live SKU list.
  const { data: liveSkus } = useQuery({
    queryKey: ["skus", "counts-by-product"],
    queryFn: () => skusApi.list({ limit: 1000, active_only: false }),
    retry: 1,
  });
  const skuCountMap: Record<string, number> = useMemo(() => {
    const map: Record<string, number> = {};
    (liveSkus ?? []).forEach((s) => {
      map[s.product_id] = (map[s.product_id] ?? 0) + 1;
    });
    return map;
  }, [liveSkus]);

  const statuses: FilterStatus[] = ["all", "active", "seasonal", "pre_launch", "clearance", "discontinued"];
  return (
    <div className="space-y-4 animate-fade-in" data-industry={industry}>
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold text-white mb-3"
            style={{ background: gradient }}
          >
            {icon} {displayName}
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Product Catalogue
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-xl leading-relaxed">
            All products in this industry. Each product groups one or more SKUs that carry pricing, lead time, and stock parameters for forecasting.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            icon={<FileSpreadsheet size={14} />}
            onClick={() => exportApi.productsCsv().catch(() => toast.error("Export failed"))}
            className="glass border border-slate-200 dark:border-slate-700"
          >
            Export CSV
          </Button>
          <Button
            variant="secondary"
            icon={<FileSpreadsheet size={14} />}
            onClick={() => {
              setAddProductOpen(true);
              setModalTab("import");
            }}
            className="glass border border-slate-200 dark:border-slate-700"
          >
            Import CSV
          </Button>
          <Button
            icon={<Plus size={14} />}
            onClick={() => {
              setAddProductOpen(true);
              setModalTab("manual");
            }}
            className="btn-primary"
          >
            New Product
          </Button>
        </div>
      </div>

      {/* ── Summary KPIs ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Total Products", value: products.length.toString(), sub: "In this catalogue", icon: <Package size={15} />, tone: "default" },
          { label: "Active", value: activeCount.toString(), sub: "Live in market", icon: <CheckCircle2 size={15} />, tone: "up" },
          { label: "Categories", value: categories_count.toString(), sub: `${categoryHints.slice(0, 2).join(", ")}…`, icon: <Tag size={15} />, tone: "default" },
          { label: "Pre-Launch", value: prelaunchCount.toString(), sub: "Coming soon", icon: <Star size={15} />, tone: prelaunchCount > 0 ? "warn" : "default" },
        ].map(({ label, value, sub, icon: ic, tone }) => (
          <div key={label} className="glass rounded-2xl p-4">
            <div className={clsx(
              "h-8 w-8 rounded-lg flex items-center justify-center mb-3",
              tone === "up" ? "bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400" :
              tone === "warn" ? "bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400" :
              "bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400"
            )}>
              {ic}
            </div>
            <div className="text-2xl font-black text-slate-900 dark:text-white">{value}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mt-0.5">{label}</div>
            <div className="text-[10px] text-slate-400 dark:text-slate-500">{sub}</div>
          </div>
        ))}
      </div>

      {/* ── Controls bar ── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="flex-1 min-w-48 max-w-72">
          <Input
            icon={<Search size={14} />}
            placeholder="Search name, brand, category…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {/* Status filter pills */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/60 rounded-xl p-1">
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-[10px] font-bold capitalize transition-all whitespace-nowrap",
                filterStatus === s
                  ? "bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm"
                  : "text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300"
              )}
            >
              {s === "all" ? "All" : STATUS_CONFIG[s as ProductStatus]?.label}
            </button>
          ))}
        </div>

        {/* Category filter */}
        <div className="flex items-center gap-2">
          <Filter size={13} className="text-slate-400 dark:text-slate-500" />
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="text-xs font-semibold text-slate-600 dark:text-slate-300 bg-transparent border-none outline-none cursor-pointer"
          >
            <option value="all">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {/* View toggle */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/60 rounded-xl p-1 ml-auto">
          <button
            onClick={() => setViewMode("grid")}
            className={clsx("p-1.5 rounded-lg transition", viewMode === "grid" ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100" : "text-slate-400 dark:text-slate-500")}
          >
            <LayoutGrid size={14} />
          </button>
          <button
            onClick={() => setViewMode("list")}
            className={clsx("p-1.5 rounded-lg transition", viewMode === "list" ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100" : "text-slate-400 dark:text-slate-500")}
          >
            <List size={14} />
          </button>
        </div>
      </div>

      {/* ── Product Grid / List ── */}
      {products.length === 0 ? (
        <div className="glass rounded-2xl p-16 text-center">
          <Package size={32} className="mx-auto text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">Your Product Catalogue is Empty</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Import a product catalog via CSV or click "New Product" to get started.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass rounded-2xl p-16 text-center">
          <Package size={32} className="mx-auto text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">No products match your search</p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Try adjusting your filter or search term</p>
        </div>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((p) => (
            <ProductCard
              key={p.id}
              product={p}
              accent={accent}
              gradient={gradient}
              images={images}
              skuCountMap={skuCountMap}
              onClick={() => navigate(`/workspace/products/${p.id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="glass rounded-2xl overflow-hidden">
          {/* List header */}
          <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-100 dark:border-slate-700/40 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            <div className="w-1 shrink-0" />
            <div className="w-10 shrink-0" />
            <div className="flex-1">Product</div>
            <div className="w-24 hidden sm:block">Status</div>
            <div className="w-16 text-center hidden md:block">SKUs</div>
            <div className="w-24 text-right hidden lg:block">Updated</div>
            <div className="w-4 shrink-0" />
          </div>
          <div className="divide-y divide-slate-100/60 dark:divide-slate-700/30 p-2">
            {filtered.map((p) => (
              <ProductRow
                key={p.id}
                product={p}
                gradient={gradient}
                images={images}
                skuCountMap={skuCountMap}
                onClick={() => navigate(`/workspace/products/${p.id}`)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Count */}
      <p className="text-[11px] text-slate-400 dark:text-slate-500 text-center">
        Showing <strong className="text-slate-600 dark:text-slate-300">{filtered.length}</strong> of <strong className="text-slate-600 dark:text-slate-300">{products.length}</strong> products
      </p>

      {/* ── Unified Add / Import Modal ── */}
      <ImportModal
        open={addProductOpen}
        onClose={() => {
          setAddProductOpen(false);
          setUploadFile(null);
        }}
        defaultTab={modalTab}
        title="Import Products"
        description="Upload a CSV or Excel file to bulk-add products from your warehouse catalog"
        requiredColumns={PRODUCT_REQUIRED_COLUMNS}
        optionalColumns={PRODUCT_ALL_COLUMNS.filter(
          (c) => !PRODUCT_REQUIRED_COLUMNS.includes(c as (typeof PRODUCT_REQUIRED_COLUMNS)[number]),
        )}
        tip='Use "external_id" to link SKUs later. Duplicates (same external_id) are automatically skipped.'
        onDownloadTemplate={downloadProductTemplate}
        onParse={async (file) => {
          const parsed = await parseFile(file);
          const validation = validateProductRows(parsed.rows);
          return { parsed, validation };
        }}
        onImport={async (rows, onProgress) => {
          const result = await productsApi.bulkCreate(rows, onProgress);
          qc.invalidateQueries({ queryKey: ["products"] });
          if (result.created > 0) {
            toast.success(`${result.created} product${result.created !== 1 ? "s" : ""} imported`);
          }
          return result;
        }}
        manualEntry={{
          label: "Single Product",
          submitLabel: "Create Product",
          isSubmitting: create.isPending,
          onSubmit: () => {
            const form = document.getElementById("create-product-form") as HTMLFormElement;
            form?.requestSubmit();
          },
          content: (
            <form
              id="create-product-form"
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                create.mutate({
                  name: String(fd.get("name") ?? ""),
                  brand: (fd.get("brand") as string) || undefined,
                  category: String(fd.get("category") ?? ""),
                  subcategory: (fd.get("subcategory") as string) || undefined,
                  external_id: (fd.get("external_id") as string) || undefined,
                });
              }}
            >
              {/* Image upload */}
              <div className="space-y-2">
                <span className="label">Product Image (optional)</span>
                <div className="flex items-center gap-4">
                  <div className="h-16 w-16 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-50 dark:bg-slate-900/60 flex items-center justify-center shadow-inner shrink-0 relative group/upload">
                    {uploadFile ? (
                      <>
                        <img src={uploadFile} alt="Preview" className="h-full w-full object-cover" />
                        <button
                          type="button"
                          onClick={() => setUploadFile(null)}
                          className="absolute inset-0 bg-black/50 opacity-0 group-hover/upload:opacity-100 transition-opacity flex items-center justify-center text-white text-[10px] font-bold cursor-pointer border-none"
                        >
                          Remove
                        </button>
                      </>
                    ) : (
                      <ImageIcon size={20} className="text-slate-300 dark:text-slate-600" />
                    )}
                  </div>
                  <label className="flex-1 flex flex-col items-center justify-center border border-dashed border-slate-200/80 dark:border-slate-800/60 rounded-2xl py-3 px-4 hover:border-violet-400 hover:bg-violet-50/10 transition-all duration-200 cursor-pointer select-none">
                    <Upload size={14} className="text-violet-500 mb-1" />
                    <span className="text-xs font-bold text-slate-705 dark:text-slate-200">Choose Image</span>
                    <span className="text-[10px] text-slate-400 dark:text-slate-550 mt-0.5">PNG, JPG or WEBP</span>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          const reader = new FileReader();
                          reader.onloadend = () => setUploadFile(reader.result as string);
                          reader.readAsDataURL(file);
                        }
                      }}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>

              <Input name="name" label="Product Name" required placeholder="e.g. My Product" />
              
              <div className="grid grid-cols-2 gap-3">
                <Input name="brand" label="Brand" placeholder="e.g. Apex Tech" />
                <Input name="external_id" label="External ID" placeholder="Your internal ID" />
              </div>
              
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="label">Category</label>
                  <select
                    name="category"
                    required
                    className="input w-full bg-white dark:bg-slate-900/50"
                  >
                    <option value="">Select category…</option>
                    {categoryHints.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <Input name="subcategory" label="Subcategory" placeholder="Optional" />
              </div>
            </form>
          ),
        }}
      />
    </div>
  );
};
