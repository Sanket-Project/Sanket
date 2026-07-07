import { useState, useEffect, useRef } from "react";
import clsx from "clsx";
import { Shirt, Cpu, Pill, Sprout, Wrench, ChevronDown, Check, type LucideIcon } from "lucide-react";
import { useIndustryStore } from "@/stores/industry";
import { useQueryClient } from "@tanstack/react-query";
import type { IndustryCode } from "@/types/api";
import { INDUSTRY_THEME } from "@/utils/colors";

const OPTIONS: {
  code: IndustryCode;
  label: string;
  description: string;
  Icon: LucideIcon;
}[] = [
  { code: "fashion", label: "Fashion & Apparel", description: "Trend velocity & SS26 assortment tracking", Icon: Shirt },
  { code: "electronics", label: "Consumer Electronics", description: "Component shortages & high-tech forecasts", Icon: Cpu },
  { code: "pharma", label: "Pharmaceuticals", description: "GxP compliance & batch shelf-life analytics", Icon: Pill },
  { code: "agrocenter", label: "Agrocenter", description: "Agricultural supply chain & crop yield logic", Icon: Sprout },
  { code: "hardware", label: "Tools & Hardware", description: "Retail inventory & machinery logistics", Icon: Wrench },
];

export const IndustrySwitcher = () => {
  const active = useIndustryStore((s) => s.activeIndustry);
  const set = useIndustryStore((s) => s.setIndustry);
  const qc = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const change = (code: IndustryCode) => {
    // Cancel any in-flight queries first so stale responses from the previous
    // industry cannot overwrite the new industry's data after the switch.
    void qc.cancelQueries();
    set(code);
    qc.invalidateQueries();
    setIsOpen(false);
  };

  const activeOption = OPTIONS.find((o) => o.code === active) || OPTIONS[0];
  const ActiveIcon = activeOption.Icon;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={clsx(
          "inline-flex items-center gap-3 pl-2.5 pr-4 py-2 rounded-xl text-left border transition-all duration-200 select-none cursor-pointer active:scale-[0.98] shadow-sm",
          isOpen
            ? "border-line-strong bg-surface-2"
            : "border-line bg-surface hover:bg-surface-2 hover:border-line-strong",
        )}
      >
        <span
          className="grid place-items-center h-8 w-8 rounded-lg text-white shrink-0 shadow-sm"
          style={{ background: INDUSTRY_THEME[active].gradient }}
        >
          <ActiveIcon size={14} />
        </span>
        <div className="min-w-[110px] leading-none">
          <p className="text-[9px] font-bold uppercase tracking-widest text-content-subtle">
            Workspace
          </p>
          <h4 className="font-heading text-xs font-semibold text-content mt-1.5 tracking-tight">
            {activeOption.label}
          </h4>
        </div>
        <ChevronDown
          size={14}
          className={clsx("text-content-subtle transition-transform duration-200 shrink-0", isOpen && "rotate-180")}
        />
      </button>

      {/* Menu */}
      {isOpen && (
        <div className="absolute left-0 mt-2 w-80 rounded-2xl border border-line bg-surface shadow-lg overflow-hidden animate-slide-up z-50 p-2">
          <p className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-content-subtle">
            Switch industry segment
          </p>
          <div className="space-y-0.5 max-h-[340px] overflow-y-auto">
            {OPTIONS.map(({ code, label, description, Icon }) => {
              const isActive = active === code;
              return (
                <button
                  key={code}
                  onClick={() => change(code)}
                  className={clsx(
                    "w-full flex items-center justify-between gap-3 p-2.5 rounded-xl text-left transition-colors duration-150 cursor-pointer",
                    isActive ? "bg-surface-3" : "hover:bg-surface-2",
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className="grid place-items-center h-8 w-8 rounded-lg text-white shrink-0"
                      style={{ background: INDUSTRY_THEME[code].gradient }}
                    >
                      <Icon size={16} />
                    </span>
                    <div className="min-w-0">
                      <p
                        className="font-heading text-[13px] font-semibold tracking-tight truncate"
                        style={{ color: isActive ? INDUSTRY_THEME[code].accent : "var(--text)" }}
                      >
                        {label}
                      </p>
                      <p className="text-xs text-content-subtle mt-0.5 truncate">{description}</p>
                    </div>
                  </div>
                  {isActive && (
                    <Check size={16} className="shrink-0 stroke-[2.5]" style={{ color: INDUSTRY_THEME[code].accent }} />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
