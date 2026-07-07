import clsx from "clsx";
import { useWebSocket } from "@/hooks/useWebSocket";

export const LiveIndicator = ({ className }: { className?: string }) => {
  const { isConnected } = useWebSocket();
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 text-xs font-medium",
        isConnected ? "text-emerald-600" : "text-slate-400",
        className,
      )}
      title={isConnected ? "Real-time stream connected" : "Reconnecting…"}
    >
      <span
        className={clsx(
          "h-2 w-2 rounded-full",
          isConnected
            ? "bg-emerald-500 animate-pulse"
            : "bg-slate-400",
        )}
      />
      {isConnected ? "Live" : "Offline"}
    </span>
  );
};
