import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { X } from "lucide-react";
import { Header } from "../components/Header";
import { Sidebar } from "../components/Sidebar";
import { useLogs } from "../hooks/useLogs";
import { useNotifications } from "../components/Notifications";

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { logs, ready } = useLogs();
  const { notify } = useNotifications();
  const lastNotifiedId = useRef(0);
  const initializedNotifications = useRef(false);

  useEffect(() => {
    if (!ready) return;
    if (!initializedNotifications.current) {
      lastNotifiedId.current = logs.length ? logs[logs.length - 1].event_id : 0;
      initializedNotifications.current = true;
      return;
    }
    const newEvents = logs.filter((event) => event.event_id > lastNotifiedId.current);
    if (newEvents.length === 0) return;
    lastNotifiedId.current = newEvents[newEvents.length - 1].event_id;
    for (const event of newEvents) {
      if (event.event === "execution.day_completed") continue;
      if (["day_completed", "execution_finished"].includes(event.event)) {
        notify(event.message);
      } else if (event.event === "execution.failed") {
        notify(event.message, "error");
      } else {
        continue;
      }
      if (document.visibilityState === "hidden" && "Notification" in window && Notification.permission === "granted") {
        new Notification("AutoDev execution update", { body: event.message });
      }
    }
  }, [logs, notify, ready]);

  return (
    <div className="min-h-screen bg-canvas text-slate-100">
      <Sidebar />
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/70 lg:hidden" onClick={() => setMobileOpen(false)}>
          <div className="absolute inset-y-0 left-0 w-72 bg-[#0b101d] p-4" onClick={(event) => event.stopPropagation()}>
            <button onClick={() => setMobileOpen(false)} className="mb-4 ml-auto flex rounded-lg p-2 text-muted" aria-label="Close navigation"><X className="size-5" /></button>
            <MobileNav close={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
      <div className="min-h-screen lg:pl-64">
        <Header onMenu={() => setMobileOpen(true)} />
        <main className="mx-auto min-h-[calc(100vh-130px)] max-w-[1440px] px-5 py-7 sm:px-8 lg:px-10">
          <Outlet />
        </main>
        <footer className="border-t border-line/70 px-5 py-4 text-center text-[11px] text-slate-600 sm:px-8 lg:px-10">
          AutoDev Engineering OS <span className="mx-2 text-slate-700">·</span> Version 6.0 <span className="mx-2 text-slate-700">·</span> Your AI engine stays in the backend
        </footer>
      </div>
    </div>
  );
}

function MobileNav({ close }: { close: () => void }) {
  const items = [
    ["/", "Dashboard"],
    ["/projects", "Projects"],
    ["/execution", "Execution"],
    ["/roadmap", "Roadmap"],
    ["/history", "History"],
    ["/settings", "Settings"],
  ];
  return <nav className="flex flex-col gap-1">{items.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"} onClick={close} className={({ isActive }) => `rounded-xl px-3 py-2.5 text-sm ${isActive ? "bg-brand/10 text-violet-200" : "text-slate-400 hover:bg-white/5"}`}>{label}</NavLink>)}</nav>;
}
