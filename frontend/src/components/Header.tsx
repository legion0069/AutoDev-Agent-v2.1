import { useEffect, useState } from "react";
import { Bell, Circle, Menu, Search } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useApiHealth } from "../hooks/useProject";

const pageNames: Record<string, string> = {
  "/": "Dashboard",
  "/projects": "Projects",
  "/execution": "Execution",
  "/roadmap": "Roadmap",
  "/history": "History",
  "/settings": "Settings",
};

export function Header({ onMenu }: { onMenu: () => void }) {
  const { pathname } = useLocation();
  const health = useApiHealth();
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  const connected = online && health.isSuccess;

  return (
    <header className="sticky top-0 z-20 flex h-[76px] items-center justify-between border-b border-line/80 bg-canvas/90 px-5 backdrop-blur-xl sm:px-8">
      <div className="flex items-center gap-3">
        <button onClick={onMenu} className="rounded-lg p-2 text-muted hover:bg-white/5 lg:hidden" aria-label="Open navigation"><Menu className="size-5" /></button>
        <div>
          <p className="text-xs text-muted">Workspace / <span className="text-slate-300">{pageNames[pathname] ?? "AutoDev"}</span></p>
          <h1 className="mt-0.5 text-lg font-semibold tracking-tight text-white">{pageNames[pathname] ?? "AutoDev"}</h1>
        </div>
      </div>
      <div className="flex items-center gap-3 sm:gap-5">
        <div className="hidden items-center gap-2 rounded-full border border-line bg-panel/80 px-3 py-1.5 text-xs text-muted sm:flex">
          <Circle className={`size-2.5 fill-current ${connected ? "text-mint" : "text-rose-400"}`} />
          {connected ? "Backend connected" : online ? "Backend offline" : "You are offline"}
        </div>
        <button aria-label="Search" className="hidden rounded-lg p-2 text-muted hover:bg-white/5 sm:block"><Search className="size-[18px]" /></button>
        <button aria-label="Notifications" className="relative rounded-lg p-2 text-muted hover:bg-white/5">
          <Bell className="size-[18px]" /><span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-brand" />
        </button>
        <div className="flex size-8 items-center justify-center rounded-full border border-violet-300/20 bg-violet-400/10 text-xs font-semibold text-violet-200">AD</div>
      </div>
    </header>
  );
}
