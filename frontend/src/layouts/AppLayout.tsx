import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { X } from "lucide-react";
import { Header } from "../components/Header";
import { Sidebar } from "../components/Sidebar";

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
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
          AutoDev Engineering OS <span className="mx-2 text-slate-700">·</span> Version 5.1 <span className="mx-2 text-slate-700">·</span> Your AI engine stays in the backend
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
