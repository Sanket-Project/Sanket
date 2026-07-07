import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useWebSocket, type RealtimeEvent } from "@/hooks/useWebSocket";
import { fmtRelative } from "@/utils/format";

const EVENT_BADGE: Record<string, "info" | "success" | "warning" | "danger" | "primary"> = {
  "forecast.run.progress": "info",
  "forecast.run.completed": "success",
  "forecast.run.failed": "danger",
  "signal.validated": "success",
  "pharma_batch.released": "success",
  "pharma_batch.recalled": "danger",
  "subscription.updated": "primary",
  "usage.quota_warning": "warning",
  "usage.quota_exceeded": "danger",
  "connection.ready": "info",
};

export const EventFeed = ({ maxEvents = 25 }: { maxEvents?: number }) => {
  const { subscribe, isConnected } = useWebSocket();
  const [events, setEvents] = useState<RealtimeEvent[]>([]);

  useEffect(
    () =>
      subscribe((e) =>
        setEvents((prev) => [e, ...prev].slice(0, maxEvents)),
      ),
    [subscribe, maxEvents],
  );

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Activity size={16} /> Live event feed
        </span>
      }
      description={isConnected ? "Streaming…" : "Reconnecting"}
    >
      {events.length === 0 ? (
        <div className="text-sm text-slate-400 py-6 text-center">
          No events yet. Generate a forecast or validate a signal to see live updates.
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 max-h-[360px] overflow-y-auto">
          {events.map((e) => (
            <li key={e.event_id} className="py-2.5 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <Badge variant={EVENT_BADGE[e.type] ?? "info"}>{e.type}</Badge>
                <div className="text-xs text-slate-500 mt-1 truncate">
                  {Object.entries(e.data)
                    .slice(0, 3)
                    .map(([k, v]) => `${k}=${String(v).slice(0, 30)}`)
                    .join(" · ")}
                </div>
              </div>
              <span className="text-[10px] text-slate-400 whitespace-nowrap">
                {fmtRelative(e.occurred_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
