import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";

type Toast = { id: number; message: string; type: "success" | "error" };
type NotificationsApi = { notify: (message: string, type?: Toast["type"]) => void };

const NotificationsContext = createContext<NotificationsApi | null>(null);

export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const notify = useCallback((message: string, type: Toast["type"] = "success") => {
    const id = Date.now() + Math.random();
    setItems((current) => [...current, { id, message, type }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 5000);
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <NotificationsContext.Provider value={value}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((item) => (
          <div key={item.id} className="flex items-start gap-3 rounded-xl border border-line bg-panel p-4 shadow-glow">
            {item.type === "success" ? <CheckCircle2 className="mt-0.5 size-4 text-mint" /> : <AlertCircle className="mt-0.5 size-4 text-rose-400" />}
            <p className="flex-1 text-sm text-slate-200">{item.message}</p>
            <button aria-label="Dismiss notification" onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}>
              <X className="size-4 text-muted" />
            </button>
          </div>
        ))}
      </div>
    </NotificationsContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationsContext);
  if (!context) throw new Error("useNotifications must be used within NotificationsProvider.");
  return context;
}
