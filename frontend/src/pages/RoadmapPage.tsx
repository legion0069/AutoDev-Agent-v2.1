import { useState } from "react";
import { ArrowDown, CheckCircle2, FlaskConical, ListTodo } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";
import { PageHeading } from "../components/PageHeading";
import { RoadmapCard } from "../components/RoadmapCard";
import { useRoadmap } from "../hooks/useProject";

export function RoadmapPage() {
  const roadmap = useRoadmap();
  const [selectedDay, setSelectedDay] = useState(1);
  const dayQuery = useQuery({
    queryKey: ["roadmap-day", selectedDay],
    queryFn: () => apiService.day(selectedDay),
    enabled: Boolean(roadmap.data?.days.length),
    retry: 1,
  });
  const selected = dayQuery.data ?? roadmap.data?.days.find((day) => day.day === selectedDay);
  return (
    <div>
      <PageHeading title="Roadmap" subtitle="A focused, day-by-day view of project goals, tasks, and validation." />
      {roadmap.isLoading ? <div className="h-60 animate-pulse rounded-2xl bg-panel" /> : roadmap.isError ? <div role="alert" className="rounded-2xl border border-dashed border-line bg-panel/40 p-10 text-center"><ListTodo className="mx-auto size-7 text-slate-600" /><p className="mt-3 text-sm text-slate-300">No roadmap available</p><p className="mt-1 text-xs text-muted">Create a project first to generate a roadmap.</p></div> : (
        <div className="grid items-start gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <section><div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold text-white">Milestones</h3><span className="text-xs text-muted">{roadmap.data?.days.length} days</span></div><div className="space-y-3">{roadmap.data?.days.map((day) => <RoadmapCard key={day.day} day={day} active={selectedDay === day.day} onClick={() => setSelectedDay(day.day)} />)}</div></section>
          {selected && <section className="sticky top-24 rounded-2xl border border-line bg-panel/70 p-5 sm:p-6">
            <div className="flex items-start justify-between gap-4"><div><span className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">Day {selected.day}</span><h3 className="mt-2 text-xl font-semibold text-white">{selected.phase_name}</h3></div><span className={`rounded-full px-2.5 py-1 text-[10px] capitalize ${selected.status === "completed" ? "bg-mint/10 text-mint" : selected.status === "in_progress" ? "bg-brand/10 text-violet-200" : "bg-surface text-slate-500"}`}>{selected.status.replace("_", " ")}</span></div>
            <Section title="Goals" icon={<CheckCircle2 className="size-4 text-violet-300" />} items={selected.goals} />
            <Section title="Tasks" icon={<ListTodo className="size-4 text-violet-300" />} items={selected.tasks} />
            <Section title="Deliverables" icon={<ArrowDown className="size-4 text-violet-300" />} items={selected.deliverables} />
            <Section title="Validation" icon={<FlaskConical className="size-4 text-mint" />} items={selected.tests} />
            <div className="mt-6 rounded-xl border border-line bg-surface/50 p-4"><div className="flex items-center gap-2"><FlaskConical className="size-4 text-mint" /><p className="text-xs font-medium text-slate-200">Testing focus</p></div><p className="mt-2 text-xs leading-5 text-slate-400">{selected.testing_focus}</p></div>
            <div className="mt-4 flex items-center justify-between text-xs"><span className="text-muted">Commits</span><span className="text-slate-300">{selected.commits?.length ?? 0}</span></div>
            {dayQuery.isFetching && <p className="mt-3 text-[11px] text-muted">Refreshing milestone details…</p>}
          </section>}
        </div>
      )}
    </div>
  );
}

function Section({ title, icon, items }: { title: string; icon: React.ReactNode; items: string[] }) {
  return <div className="mt-6"><div className="mb-2 flex items-center gap-2">{icon}<h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">{title}</h4></div><ul className="space-y-2">{items?.map((item, index) => <li key={`${item}-${index}`} className="flex gap-2 text-xs leading-5 text-slate-400"><span className="mt-2 size-1 shrink-0 rounded-full bg-slate-600" />{item}</li>)}</ul></div>;
}
