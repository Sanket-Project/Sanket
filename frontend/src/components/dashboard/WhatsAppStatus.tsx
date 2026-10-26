import { useQuery } from "@tanstack/react-query";

import { notificationsApi } from "@/api/notifications";
import { AlertTriangle, Check, Info } from "@/components/ui/icons";
import { whatsAppReadiness, type WhatsAppState } from "@/utils/whatsAppReadiness";

export const WhatsAppStatus = () => {
  const { data, isError, isLoading } = useQuery({
    queryKey: ["whatsapp-config"],
    queryFn: () => notificationsApi.getWhatsApp(),
    staleTime: 60_000,
  });
  const status = isLoading
    ? { state: "error" as WhatsAppState, label: "Checking…", detail: "" }
    : whatsAppReadiness(data, isError);
  const Icon = status.state === "ready" ? Check : status.state === "error" ? Info : AlertTriangle;
  const tone = status.state === "ready" ? "text-emerald-600" : "text-amber-600";

  return (
    <div className="flex items-center gap-3">
      <Icon size={17} className={tone} />
      <div>
        <dt className="text-xs font-semibold text-content">WhatsApp delivery</dt>
        <dd className="text-xs text-content-subtle" title={status.detail}>
          {status.label}
        </dd>
      </div>
    </div>
  );
};
