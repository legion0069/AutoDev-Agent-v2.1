import { NavLink } from "react-router-dom";
import {
  Activity,
  Blocks,
  ChevronLeft,
  CircleHelp,
  Clock3,
  LayoutDashboard,
  ListTodo,
  Settings2,
  Sparkles,
} from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "Projects", icon: Blocks },
  { to: "/execution", label: "Execution", icon: Activity },
  { to: "/roadmap", label: "Roadmap", icon: ListTodo },
  { to: "/history", label: "History", icon: Clock3 },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-line bg-[#0b101d] px-4 py-5 lg:flex">
      <NavLink to="/" className="mb-10 flex items-center gap-3 px-2">
        <span className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-indigo-400 shadow-glow">
          <Sparkles className="size-5 text-white" />
        </span>
        <span>
          <span className="block text-base font-semibold tracking-tight text-white">AutoDev</span>
          <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted">Engineering OS</span>
        </span>
      </NavLink>
      <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">Workspace</p>
      <nav className="flex flex-col gap-1">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? "bg-brand/10 text-violet-200 ring-1 ring-inset ring-brand/20"
                  : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-100"
              }`
            }
          >
            <Icon className="size-[18px] opacity-80" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto">
        <div className="rounded-2xl border border-line bg-panel/70 p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex size-8 items-center justify-center rounded-lg bg-brand/10 text-brand"><CircleHelp className="size-4" /></span>
            <ChevronLeft className="size-4 text-slate-600" />
          </div>
          <p className="text-sm font-medium text-slate-200">Build with focus</p>
          <p className="mt-1 text-xs leading-5 text-muted">Your roadmap, execution, and engineering signals in one place.</p>
        </div>
        <div className="mt-4 flex items-center justify-between px-2 text-[11px] text-slate-600">
          <span>AutoDev UI</span><span>v5.1</span>
        </div>
      </div>
    </aside>
  );
}
