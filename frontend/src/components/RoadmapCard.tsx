import { Check, Circle, Clock3, GitCommitHorizontal } from "lucide-react";
import type { RoadmapDay } from "../types";
import { ProgressBar } from "./ProgressBar";

export function RoadmapCard({ day, onClick, active }: { day: RoadmapDay; onClick: () => void; active: boolean }) {
  const done = day.status === "completed";
  return (
    <button onClick={onClick} className={`w-full rounded-2xl border p-4 text-left transition ${active ? "border-brand/40 bg-brand/[0.06]" : "border-line bg-panel/60 hover:border-slate-700"}`}>
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ${done ? "bg-emerald-400/10 text-mint" : day.status === "in_progress" ? "bg-brand/10 text-violet-300" : "bg-surface text-slate-500"}`}>
          {done ? <Check className="size-4" /> : day.status === "in_progress" ? <Clock3 className="size-4" /> : <Circle className="size-3" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2"><span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Day {day.day}</span><span className={`text-[10px] capitalize ${done ? "text-mint" : day.status === "in_progress" ? "text-violet-300" : "text-slate-600"}`}>{day.status.replace("_", " ")}</span></div>
          <p className="mt-1 truncate text-sm font-medium text-slate-200">{day.phase_name}</p>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{day.goals?.[0]}</p>
          <div className="mt-3 flex items-center gap-4 text-[11px] text-slate-500"><span className="flex items-center gap-1"><GitCommitHorizontal className="size-3.5" />{day.commits?.length ?? 0} commits</span><span>{day.tasks?.length ?? 0} tasks</span></div>
          <div className="mt-3"><ProgressBar value={day.completion} /></div>
        </div>
      </div>
    </button>
  );
}
