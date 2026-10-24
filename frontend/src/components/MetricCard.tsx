import type { LucideIcon } from "lucide-react";

export function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  accent = "violet",
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
  accent?: "violet" | "mint" | "blue" | "amber";
}) {
  const colors = {
    violet: "bg-violet-400/10 text-violet-300",
    mint: "bg-emerald-400/10 text-mint",
    blue: "bg-sky-400/10 text-sky-300",
    amber: "bg-amber-400/10 text-amber-300",
  };
  return (
    <div className="rounded-2xl border border-line bg-panel/70 p-5 transition hover:border-slate-700">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted">{label}</p>
        <span className={`flex size-9 items-center justify-center rounded-xl ${colors[accent]}`}><Icon className="size-[18px]" /></span>
      </div>
      <p className="mt-4 text-2xl font-semibold tracking-tight text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  );
}
