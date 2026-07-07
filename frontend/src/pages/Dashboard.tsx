import { useIndustryStore } from "@/stores/industry";
import { FashionDashboard } from "@/pages/industries/FashionDashboard";
import { ElectronicsDashboard } from "@/pages/industries/ElectronicsDashboard";
import { PharmaDashboard } from "@/pages/industries/PharmaDashboard";
import { AgrocenterdDashboard } from "@/pages/industries/AgrocenterdDashboard";
import { HardwareDashboard } from "@/pages/industries/HardwareDashboard";

export const Dashboard = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  if (industry === "fashion") return <FashionDashboard />;
  if (industry === "electronics") return <ElectronicsDashboard />;
  if (industry === "agrocenter") return <AgrocenterdDashboard />;
  if (industry === "hardware") return <HardwareDashboard />;
  return <PharmaDashboard />;
};
