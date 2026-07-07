import { useCallback, useRef, useState, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Upload,
  FileSpreadsheet,
  Download,
  CheckCircle,
  XCircle,
  AlertCircle,
  X,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Info,
  Layers,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { ParsedRow, ParseResult, ValidationResult } from "@/utils/csvImport";
import { useIndustryStore } from "@/stores/industry";
import { industryAccent, industryGradient, industryDisplay } from "@/utils/colors";
import clsx from "clsx";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ImportResult {
  created: number;
  skipped: number;
  failed: number;
  errors: Array<{ row: ParsedRow; reason: string }>;
}

export interface ImportModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  /** Column names expected in the file (shown in hint) */
  requiredColumns: readonly string[];
  optionalColumns?: readonly string[];
  /** Called to parse + validate the file contents */
  onParse: (file: File) => Promise<{ parsed: ParseResult; validation: ValidationResult }>;
  /** Called to run the actual bulk import — receives validated rows */
  onImport: (
    rows: ParsedRow[],
    onProgress: (done: number, total: number) => void,
  ) => Promise<ImportResult>;
  /** Download a template CSV */
  onDownloadTemplate: () => void;
  /** Extra tip shown below the column list */
  tip?: string;

  /** Manual entry configuration for single item tab */
  manualEntry?: {
    label: string;
    content: React.ReactNode;
    onSubmit: () => void | Promise<void>;
    isSubmitting?: boolean;
    submitLabel?: string;
  };
  defaultTab?: "manual" | "import";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

type Phase = "idle" | "preview" | "importing" | "done";

interface ProgressBarProps {
  done: number;
  total: number;
  accent: string;
}
const ProgressBar = ({ done, total, accent }: ProgressBarProps) => {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="space-y-3 p-4 bg-slate-50 rounded-2xl border border-slate-100">
      <div className="flex justify-between text-xs text-slate-500 font-semibold uppercase tracking-wider">
        <span>Importing rows...</span>
        <span>
          {done} / {total}
        </span>
      </div>
      <div className="h-3 bg-slate-100 rounded-full overflow-hidden p-0.5 border border-slate-200">
        <div
          className="h-full rounded-full transition-all duration-300 shadow-sm"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${accent} 0%, ${accent}cc 100%)`,
          }}
        />
      </div>
      <div className="flex justify-between items-center text-[11px] text-slate-400 font-medium">
        <span>{pct}% complete</span>
        <span>Please do not refresh this page</span>
      </div>
    </div>
  );
};

const INDUSTRY_CATEGORY_GUIDELINES: Record<string, string[]> = {
  fashion: ["Women's Apparel", "Men's Apparel", "Footwear", "Accessories", "Bags"],
  electronics: ["Smartphones", "Laptops", "Audio", "Smart Home", "Tablets", "Accessories"],
  pharma: ["Oncology", "Allergy", "Metabolic", "Antibiotics", "Cardiovascular"],
  agrocenter: ["Fertilizers", "Seeds", "Pesticides", "Irrigation", "Soil Amendments"],
  hardware: ["Power Tools", "Fasteners", "Electrical", "Plumbing", "Building Materials", "Safety"],
};

// ─── Main component ───────────────────────────────────────────────────────────

export const ImportModal = ({
  open,
  onClose,
  title,
  description,
  requiredColumns,
  optionalColumns = [],
  onParse,
  onImport,
  onDownloadTemplate,
  tip,
  manualEntry,
  defaultTab = "manual",
}: ImportModalProps) => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const accent = industryAccent[industry];
  const gradient = industryGradient[industry];
  const displayName = industryDisplay[industry];

  const [activeTab, setActiveTab] = useState<"manual" | "import">("manual");
  const [phase, setPhase] = useState<Phase>("idle");
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParseResult | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [result, setResult] = useState<ImportResult | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setPhase("idle");
    setDragging(false);
    setFile(null);
    setParsed(null);
    setValidation(null);
    setProgress({ done: 0, total: 0 });
    setResult(null);
    setParseError(null);
    setShowErrors(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  // Sync tab choice with default tab prop when opening
  useEffect(() => {
    if (open) {
      setActiveTab(manualEntry ? defaultTab : "import");
      reset();
    }
  }, [open, defaultTab, manualEntry]);

  const processFile = useCallback(
    async (f: File) => {
      setFile(f);
      setParseError(null);
      try {
        const { parsed: p, validation: v } = await onParse(f);
        if (p.errors.length > 0 && p.rows.length === 0) {
          setParseError(p.errors[0]);
          return;
        }
        setParsed(p);
        setValidation(v);
        setPhase("preview");
      } catch (e) {
        setParseError(String(e));
      }
    },
    [onParse],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) processFile(f);
    },
    [processFile],
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) processFile(f);
    e.target.value = "";
  };

  const handleImport = async () => {
    if (!validation) return;
    setPhase("importing");
    setProgress({ done: 0, total: validation.valid.length });

    try {
      const res = await onImport(validation.valid, (done, total) => {
        setProgress({ done, total });
      });
      setResult(res);
      setPhase("done");
    } catch (e) {
      setResult({
        created: 0,
        skipped: 0,
        failed: validation.valid.length,
        errors: [{ row: {}, reason: String(e) }],
      });
      setPhase("done");
    }
  };

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 py-4 sm:py-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-955/50 dark:bg-black/70 backdrop-blur-md transition-opacity duration-300"
        onClick={handleClose}
      />

      {/* Modal Container */}
      <div className="relative z-10 w-full max-w-4xl glass-strong rounded-3xl flex flex-col max-h-[90vh] overflow-hidden transition-all duration-300 scale-100">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50 gap-4">
          <div className="flex items-center gap-3.5">
            <div
              className="h-10 w-10 rounded-2xl flex items-center justify-center text-white shadow-md shadow-violet-500/10 shrink-0"
              style={{ background: gradient }}
            >
              <FileSpreadsheet size={20} />
            </div>
            <div>
              <h2 className="font-heading text-lg font-black text-slate-900 leading-tight">
                {activeTab === "manual" ? "Add New Product" : title}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {activeTab === "manual" ? "Manually fill out product details" : description}
              </p>
            </div>
          </div>

          {/* Dynamic Tab Switcher (if manualEntry exists) */}
          {manualEntry && (
            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-xl shadow-inner border border-slate-200 shrink-0 select-none">
              <button
                type="button"
                onClick={() => setActiveTab("manual")}
                className={clsx(
                  "px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all duration-200 cursor-pointer",
                  activeTab === "manual"
                    ? "bg-white text-slate-800 shadow-sm border border-slate-200"
                    : "text-slate-400 hover:text-slate-655"
                )}
              >
                {manualEntry.label}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("import")}
                className={clsx(
                  "px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all duration-200 cursor-pointer",
                  activeTab === "import"
                    ? "bg-white text-slate-800 shadow-sm border border-slate-200"
                    : "text-slate-400 hover:text-slate-655"
                )}
              >
                Bulk Import (CSV)
              </button>
            </div>
          )}

          <button
            onClick={handleClose}
            className="absolute top-4 right-4 sm:relative sm:top-0 sm:right-0 h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Dynamic Multi-Column Body */}
        <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
          
          {/* LEFT COLUMN: GUIDELINES & CONTEXT */}
          <div className="w-full md:w-[35%] bg-slate-55 border-b md:border-b-0 md:border-r border-slate-100 p-6 overflow-y-auto space-y-6 shrink-0">
            {activeTab === "manual" ? (
              // Manual Form Left Sidebar Guidelines
              <div className="space-y-5">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-455">
                    <Layers size={12} style={{ color: accent }} />
                    Target Catalogue
                  </div>
                  <h3 className="text-base font-extrabold text-slate-800">{displayName}</h3>
                </div>

                <div className="p-4 rounded-2xl bg-white border border-slate-200 space-y-3">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700">
                    <BookOpen size={13} style={{ color: accent }} />
                    Quick Guidelines
                  </div>
                  <ul className="space-y-2 text-[11px] text-slate-500 leading-relaxed list-disc pl-4">
                    <li>Required fields are marked with an asterisk (<span className="text-rose-500">*</span>).</li>
                    <li>Set an **External ID** to match SKU codes and link logistics data.</li>
                    <li>Choose a standard category. Clean taxonomies yield accurate forecast aggregations.</li>
                  </ul>
                </div>

                {/* Category Hints Drawer */}
                {INDUSTRY_CATEGORY_GUIDELINES[industry] && (
                  <div className="space-y-2.5">
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-455">
                      Standard Categories
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {INDUSTRY_CATEGORY_GUIDELINES[industry].map((cat) => (
                        <span
                          key={cat}
                          className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 text-xs font-semibold border border-slate-200"
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              // CSV Import Left Sidebar Guidelines
              <div className="space-y-5">
                {/* Template Download Card */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3">
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">Need a data template?</h4>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Download our structured CSV spreadsheet to ensure formatting matches our parser rules.
                    </p>
                  </div>
                  <button
                    onClick={onDownloadTemplate}
                    type="button"
                    className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-white border border-slate-200 text-xs font-bold text-violet-600 hover:bg-slate-50 shadow-sm transition-colors cursor-pointer"
                  >
                    <Download size={13} />
                    Download template CSV
                  </button>
                </div>

                {/* Expected columns with tags */}
                <div className="space-y-2.5">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-455">
                    File Columns Mapping
                  </div>
                  <div className="space-y-2 max-h-[160px] overflow-y-auto pr-1">
                    {requiredColumns.map((col) => (
                      <div
                        key={col}
                        className="flex items-center justify-between p-2 rounded-xl bg-slate-100 border border-slate-200 text-[11px] font-mono font-bold text-violet-700"
                      >
                        <span>{col}</span>
                        <span className="text-[9px] font-sans font-extrabold uppercase px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 tracking-wider">
                          REQ
                        </span>
                      </div>
                    ))}
                    {optionalColumns.map((col) => (
                      <div
                        key={col}
                        className="flex items-center justify-between p-2 rounded-xl bg-slate-55 border border-slate-200 text-[11px] font-mono text-slate-500"
                      >
                        <span>{col}</span>
                        <span className="text-[9px] font-sans font-bold uppercase text-slate-400">
                          OPT
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {tip && (
                  <div className="flex items-start gap-2 p-3.5 rounded-xl bg-slate-100 text-[11px] text-slate-500 border border-slate-200 leading-relaxed">
                    <Info size={14} className="shrink-0 text-slate-400 mt-0.5" />
                    <span>{tip}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* RIGHT COLUMN: WORKSPACE CONTENT */}
          <div className="flex-1 p-6 overflow-y-auto flex flex-col justify-between bg-white">
            {activeTab === "manual" ? (
              // MANUAL FORM VIEW
              <div className="space-y-4">{manualEntry?.content}</div>
            ) : (
              // BULK IMPORT FLOW VIEW
              <div className="space-y-5 flex-1">
                
                {/* ── PHASE: IDLE (DRAG & DROP ZONE) ── */}
                {phase === "idle" && (
                  <div className="space-y-4">
                    <div
                      onDrop={handleDrop}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragging(true);
                      }}
                      onDragLeave={() => setDragging(false)}
                      onClick={() => inputRef.current?.click()}
                      style={{
                        borderColor: dragging ? accent : undefined,
                        boxShadow: dragging ? `0 0 0 4px ${accent}15` : undefined,
                        background: dragging ? `${accent}0a` : undefined,
                      }}
                      className={clsx(
                        "border-2 border-dashed rounded-3xl p-12 flex flex-col items-center justify-center gap-4 cursor-pointer transition-all duration-300",
                        dragging
                          ? "scale-[1.01]"
                          : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                      )}
                    >
                      <div className="h-16 w-16 rounded-2xl bg-slate-100 flex items-center justify-center shadow-inner group-hover:scale-105 transition-transform duration-300">
                        <Upload size={28} className="text-slate-400 animate-bounce" />
                      </div>
                      <div className="text-center space-y-1">
                        <h4 className="font-heading text-sm font-extrabold text-slate-800">
                          {dragging ? "Release to upload" : "Upload your inventory file"}
                        </h4>
                        <p className="text-xs text-slate-400">
                          Drag and drop files here, or <span className="text-violet-500 font-bold hover:underline">browse files</span>
                        </p>
                      </div>
                      <span className="text-[10px] uppercase font-bold tracking-wider text-slate-300 bg-slate-50 px-2.5 py-0.5 rounded border border-slate-200">
                        CSV or Excel (.xlsx, .xls)
                      </span>
                      <input
                        ref={inputRef}
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        className="hidden"
                        onChange={handleFileChange}
                      />
                    </div>
                  </div>
                )}

                {parseError && (
                  <div className="flex items-start gap-2.5 rounded-2xl bg-rose-50 border border-rose-200 p-4 text-xs font-medium text-rose-800">
                    <XCircle size={16} className="shrink-0 mt-0.5 text-rose-500" />
                    <span>{parseError}</span>
                  </div>
                )}

                {/* ── PHASE: PREVIEW (FILE DETECTED) ── */}
                {phase === "preview" && parsed && validation && (
                  <div className="space-y-4">
                    {/* Header: File info */}
                    <div className="flex items-center gap-3 rounded-2xl bg-slate-50 border border-slate-200 px-4 py-3">
                      <FileSpreadsheet size={20} className="text-slate-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold text-slate-800 truncate">{file?.name}</div>
                        <div className="text-[10px] text-slate-400 font-medium mt-0.5">
                          {parsed.rows.length} rows detected · {validation.valid.length} valid ·{" "}
                          {validation.invalid.length} invalid
                        </div>
                      </div>
                      <button
                        onClick={reset}
                        type="button"
                        style={{ color: accent }}
                        className="text-xs font-bold hover:underline transition-colors cursor-pointer shrink-0"
                      >
                        Change file
                      </button>
                    </div>

                    {/* Quick Stats Grid */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-3 text-center">
                        <div className="text-xl font-heading font-black text-emerald-600">{validation.valid.length}</div>
                        <div className="text-[10px] text-emerald-500 font-bold mt-0.5 uppercase tracking-wider">Ready</div>
                      </div>
                      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-3 text-center">
                        <div className="text-xl font-heading font-black text-amber-600">{validation.invalid.length}</div>
                        <div className="text-[10px] text-amber-500 font-bold mt-0.5 uppercase tracking-wider">Skipped</div>
                      </div>
                      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-3 text-center">
                        <div className="text-xl font-heading font-black text-slate-700">{parsed.rows.length}</div>
                        <div className="text-[10px] text-slate-500 font-bold mt-0.5 uppercase tracking-wider">Total</div>
                      </div>
                    </div>

                    {/* Preview Table */}
                    {parsed.rows.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                          Preview (First 5 Rows)
                        </div>
                        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
                          <table className="w-full text-xs">
                            <thead className="bg-slate-50 border-b border-slate-200">
                              <tr>
                                {parsed.headers.slice(0, 6).map((h) => (
                                  <th
                                    key={h}
                                    className="px-3 py-2 text-left font-bold text-slate-500 font-mono tracking-tight"
                                  >
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-105">
                              {parsed.rows.slice(0, 5).map((row, i) => (
                                <tr key={i} className="hover:bg-slate-50/40">
                                  {parsed.headers.slice(0, 6).map((h) => (
                                    <td key={h} className="px-3 py-2 text-slate-600 max-w-[120px] truncate">
                                      {row[h] || <span className="text-slate-300">—</span>}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Validation Warnings */}
                    {validation.invalid.length > 0 && (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => setShowErrors((v) => !v)}
                          className="w-full flex items-center justify-between px-4 py-3 text-xs font-bold text-amber-800"
                        >
                          <div className="flex items-center gap-2">
                            <AlertCircle size={14} className="text-amber-500" />
                            {validation.invalid.length} validation errors detected
                          </div>
                          {showErrors ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                        {showErrors && (
                          <div className="px-4 pb-3 space-y-1.5 max-h-32 overflow-y-auto border-t border-slate-200 pt-2.5">
                            {validation.invalid.map((err, i) => (
                              <div key={i} className="text-[11px] text-amber-700">
                                <span className="font-mono font-bold">Row {err.rowIndex}:</span>{" "}
                                {err.reason}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {validation.valid.length === 0 && (
                      <div className="flex items-center gap-2.5 rounded-2xl bg-rose-50 border border-rose-200 p-4 text-xs font-medium text-rose-800">
                        <XCircle size={15} className="text-rose-500 shrink-0" />
                        <span>No valid rows found. Please fix columns or data and select another file.</span>
                      </div>
                    )}
                  </div>
                )}

                {/* ── PHASE: IMPORTING (PROGRESS SCALING) ── */}
                {phase === "importing" && (
                  <div className="py-8">
                    <ProgressBar done={progress.done} total={progress.total} accent={accent} />
                  </div>
                )}

                {/* ── PHASE: DONE (RESULTS LOG) ── */}
                {phase === "done" && result && (
                  <div className="space-y-4">
                    <div className="flex flex-col items-center gap-3 py-4 text-center">
                      {result.failed === 0 ? (
                        <div
                          className="h-16 w-16 rounded-3xl flex items-center justify-center text-white animate-scale-in shadow-lg"
                          style={{
                            background: `linear-gradient(135deg, #10B981 0%, #059669 100%)`,
                            boxShadow: `0 8px 20px rgba(16, 185, 129, 0.25)`,
                          }}
                        >
                          <CheckCircle size={28} />
                        </div>
                      ) : (
                        <div
                          className="h-16 w-16 rounded-3xl flex items-center justify-center text-white animate-scale-in shadow-lg"
                          style={{
                            background: `linear-gradient(135deg, #F59E0B 0%, #D97706 100%)`,
                            boxShadow: `0 8px 20px rgba(245, 158, 11, 0.25)`,
                          }}
                        >
                          <AlertCircle size={28} />
                        </div>
                      )}
                      <div>
                        <h4 className="font-heading text-lg font-black text-slate-800">
                          {result.failed === 0 ? "Import Complete!" : "Import Finished with Errors"}
                        </h4>
                        <p className="text-xs text-slate-400 mt-0.5">
                          CSV rows processed successfully through API upsert.
                        </p>
                      </div>
                    </div>

                    {/* Result breakdown grids */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-3 text-center">
                        <div className="text-xl font-heading font-black text-emerald-600">{result.created}</div>
                        <div className="text-[10px] text-emerald-500 font-bold mt-0.5 uppercase tracking-wider">Created</div>
                      </div>
                      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-3 text-center">
                        <div className="text-xl font-heading font-black text-slate-500">{result.skipped}</div>
                        <div className="text-[10px] text-slate-455 font-bold mt-0.5 uppercase tracking-wider">Skipped</div>
                      </div>
                      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-3 text-center">
                        <div className="text-xl font-heading font-black text-rose-500">{result.failed}</div>
                        <div className="text-[10px] text-rose-400 font-bold mt-0.5 uppercase tracking-wider">Failed</div>
                      </div>
                    </div>

                    {result.errors.length > 0 && (
                      <div className="rounded-2xl border border-slate-205 bg-slate-50 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => setShowErrors((v) => !v)}
                          className="w-full flex items-center justify-between px-4 py-3 text-xs font-bold text-rose-800"
                        >
                          <div className="flex items-center gap-2">
                            <XCircle size={14} className="text-rose-500" />
                            {result.errors.length} rows encountered import errors
                          </div>
                          {showErrors ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                        {showErrors && (
                          <div className="px-4 pb-3 space-y-1.5 max-h-32 overflow-y-auto border-t border-slate-200 pt-2.5">
                            {result.errors.map((err, i) => (
                              <div key={i} className="text-[11px] text-rose-700">
                                <span className="font-mono font-bold">
                                  {err.row["name"] || err.row["sku_code"] || `Item ${i + 1}`}:
                                </span>{" "}
                                {err.reason}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Dynamic Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 bg-slate-50/50 shrink-0">
          {activeTab === "manual" && manualEntry ? (
            <>
              <Button
                variant="secondary"
                onClick={handleClose}
                disabled={manualEntry.isSubmitting}
                className="btn-secondary"
              >
                Cancel
              </Button>
              <Button
                loading={manualEntry.isSubmitting}
                onClick={manualEntry.onSubmit}
                style={{
                  background: manualEntry.isSubmitting ? undefined : `linear-gradient(135deg, ${accent} 0%, ${accent}dd 100%)`,
                  borderColor: accent,
                  boxShadow: `0 4px 14px ${accent}30`,
                }}
                className="text-white font-semibold flex items-center gap-1 cursor-pointer"
              >
                {manualEntry.submitLabel ?? "Create Product"}
                <ArrowRight size={14} />
              </Button>
            </>
          ) : phase === "done" ? (
            <Button onClick={handleClose} className="btn-secondary">
              Close
            </Button>
          ) : (
            <>
              <Button
                variant="secondary"
                onClick={handleClose}
                disabled={phase === "importing"}
                className="btn-secondary"
              >
                Cancel
              </Button>
              {phase === "preview" && (
                <Button
                  onClick={handleImport}
                  disabled={!validation || validation.valid.length === 0}
                  icon={<Upload size={14} />}
                  style={{
                    background: `linear-gradient(135deg, ${accent} 0%, ${accent}dd 100%)`,
                    borderColor: accent,
                    boxShadow: `0 4px 14px ${accent}30`,
                  }}
                  className="text-white font-semibold flex items-center gap-1.5 cursor-pointer animate-pulse-glow"
                >
                  Import {validation?.valid.length ?? 0} rows
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
};
