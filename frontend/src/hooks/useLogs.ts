import { createContext, createElement, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { apiBaseUrl, apiService } from "../services/api";
import type { LogEvent } from "../types";

type LogStream = { logs: LogEvent[]; connected: boolean; ready: boolean };
const LogStreamContext = createContext<LogStream | null>(null);

function useLogStream(): LogStream {
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [ready, setReady] = useState(false);
  const lastEventId = useRef(0);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let retryTimer: number | undefined;
    let retryDelay = 1000;
    let disposed = false;

    const accept = (event: LogEvent) => {
      if (!Number.isFinite(event.event_id) || event.event_id <= lastEventId.current) return;
      lastEventId.current = event.event_id;
      setLogs((current) => [...current, event]);
    };

    apiService.logs().then((initial) => {
      if (disposed) return;
      initial.forEach(accept);
      setReady(true);
    }).catch(() => {
      if (!disposed) {
        setConnected(false);
        setReady(true);
      }
    });

    const connect = () => {
      if (disposed) return;
      const wsBase = apiBaseUrl.replace(/^http/, "ws");
      socket = new WebSocket(`${wsBase}/ws/logs?after=${lastEventId.current}`);
      socket.onopen = () => {
        retryDelay = 1000;
        setConnected(true);
      };
      socket.onmessage = (message) => {
        try {
          accept(JSON.parse(message.data) as LogEvent);
        } catch {
          setConnected(false);
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) {
          retryTimer = window.setTimeout(connect, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 15_000);
        }
      };
    };
    connect();

    return () => {
      disposed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return { logs, connected, ready };
}

export function LogStreamProvider({ children }: { children: ReactNode }) {
  const { logs, connected, ready } = useLogStream();
  const stream = { logs, connected, ready };
  return createElement(LogStreamContext.Provider, { value: stream }, children);
}

export function useLogs(): LogStream {
  const stream = useContext(LogStreamContext);
  if (!stream) throw new Error("useLogs must be used within LogStreamProvider.");
  return stream;
}
