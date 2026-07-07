import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/stores/auth";

export interface RealtimeEvent {
  event_id: string;
  type: string;
  tenant_id: string;
  industry?: string;
  occurred_at: string;
  data: Record<string, unknown>;
}

type Listener = (event: RealtimeEvent) => void;

interface UseWebSocketResult {
  isConnected: boolean;
  lastEvent: RealtimeEvent | null;
  subscribe: (listener: Listener) => () => void;
}

/**
 * Tenant-scoped real-time event stream. Reconnects with exponential
 * backoff. Browsers can't set Authorization on WS — token is passed
 * as a query param.
 */
export function useWebSocket(): UseWebSocketResult {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<RealtimeEvent | null>(null);
  const listenersRef = useRef<Set<Listener>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!accessToken) {
      setIsConnected(false);
      return;
    }

    const baseUrl =
      import.meta.env.VITE_WS_BASE_URL ??
      (window.location.protocol === "https:" ? "wss://" : "ws://") +
        window.location.host;

    const connect = () => {
      const url = `${baseUrl}/ws?token=${encodeURIComponent(accessToken)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0;
        setIsConnected(true);
      };

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as RealtimeEvent;
          setLastEvent(event);
          listenersRef.current.forEach((l) => {
            try {
              l(event);
            } catch {
              /* swallow */
            }
          });
        } catch {
          // ignore non-JSON frames (e.g. "pong")
        }
      };

      ws.onclose = (e) => {
        setIsConnected(false);
        wsRef.current = null;
        if (e.code === 1008) return; // policy violation = bad token, stop trying
        const attempt = ++reconnectAttemptsRef.current;
        const delay = Math.min(30_000, 500 * 2 ** Math.min(attempt, 6));
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    // Keepalive every 25 s
    const pingTimer = window.setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 25_000);

    return () => {
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current);
      window.clearInterval(pingTimer);
      wsRef.current?.close(1000, "client unmount");
      wsRef.current = null;
    };
  }, [accessToken]);

  return {
    isConnected,
    lastEvent,
    subscribe: (listener: Listener) => {
      listenersRef.current.add(listener);
      return () => {
        listenersRef.current.delete(listener);
      };
    },
  };
}
