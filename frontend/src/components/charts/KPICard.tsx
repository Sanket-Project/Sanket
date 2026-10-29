import { memo, type ReactNode } from "react";
import { MetricTile } from "@/components/ui/MetricTile";

interface Props {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
  subtitle?: string;
}

/** Legacy entry point: recorded values only. New code uses MetricTile with explicit provenance. */
export const KPICard = memo(function KPICard({ label, value, icon, tone = "default", subtitle }: Props) {
  return <MetricTile label={label} value={value} icon={icon} tone={tone} hint={subtitle} provenance="recorded" />;
});
