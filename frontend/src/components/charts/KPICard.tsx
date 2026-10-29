import { memo, type ReactNode } from "react";
import { MetricTile, type Provenance } from "@/components/ui/MetricTile";

interface Props {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
  subtitle?: string;
  provenance?: Provenance;
}

/** Legacy entry point: defaults to recorded values. New code uses MetricTile with explicit provenance. */
export const KPICard = memo(function KPICard({ label, value, icon, tone = "default", subtitle, provenance = "recorded" }: Props) {
  // Legacy-sentinel bridge: callers still pass "Unavailable" / "—" strings until they migrate to MetricTile.
  if (value === "Unavailable" || value === "—") {
    return <MetricTile label={label} value={null} unavailableReason={subtitle} icon={icon} tone={tone} provenance={provenance} />;
  }
  return <MetricTile label={label} value={value} icon={icon} tone={tone} hint={subtitle} provenance={provenance} />;
});
