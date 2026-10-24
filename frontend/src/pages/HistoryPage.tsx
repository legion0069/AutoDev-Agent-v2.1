import { useQuery } from "@tanstack/react-query";
import { CalendarDays, GitBranch, GitCommitHorizontal, Gauge, History as HistoryIcon } from "lucide-react";
import { apiService } from "../services/api";
import { MetricCard } from "../components/MetricCard";
import { PageHeading } from "../components/PageHeading";
import { useProjectHistory } from "../hooks/useProject";

export function HistoryPage() {
  const history = useProjectHistory();
  const benchmarks = useQuery({ queryKey: ["benchmarks"], queryFn: apiService.benchmarks, retry: 1 });
  const data = history.data ?? [];
  return (
    <div>
      <PageHeading title="History & benchmarks" subtitle="Review completed projects, execution summaries, and performance reports." />
      <div className="mb-6 grid gap-4 sm:grid-cols-3"><MetricCard label="Projects tracked" value={data.length} detail="Across this workspace" icon={HistoryIcon} /><MetricCard label="Completed" value={data.filter((item) => item.status === "completed").length} detail="All planned days delivered" icon={CalendarDays} accent="mint" /><MetricCard label="Commits recorded" value={data.reduce((sum, item) => sum + (item.commits?.length ?? 0), 0)} detail="From execution metadata" icon={GitCommitHorizontal} accent="blue" /></div>
      <section className="overflow-hidden rounded-2xl border border-line bg-panel/60">
        <div className="border-b border-line p-5"><h3 className="font-semibold text-white">Execution history</h3><p className="mt-1 text-xs text-muted">Project runs, dates, and repository details</p></div>
        {history.isLoading ? <p className="p-8 text-center text-sm text-muted">Loading history…</p> : history.isError ? <p role="alert" className="p-8 text-center text-sm text-rose-300">History could not be loaded.</p> : data.length ? <div className="divide-y divide-line/70">{data.map((project) => <article key={project.project_id} className="grid gap-3 p-5 md:grid-cols-[1.5fr_0.7fr_0.7fr_1.3fr] md:items-center"><div><h4 className="text-sm font-medium text-slate-100">{project.project_name}</h4><p className="mt-1 text-xs text-slate-500">{project.completed_days} of {project.total_days} days · {project.status}</p></div><div className="text-xs text-slate-400"><CalendarDays className="mr-1.5 inline size-3.5 text-slate-600" />{new Date(project.updated_at).toLocaleDateString()}</div><div className="text-xs text-slate-400"><GitCommitHorizontal className="mr-1 inline size-4 text-slate-600" />{project.commits?.length ?? 0} commits</div>{project.repository ? <a href={project.repository} target="_blank" rel="noreferrer" className="flex min-w-0 items-center gap-2 truncate text-xs text-violet-300 hover:text-violet-200"><GitBranch className="size-3.5 shrink-0" />{project.repository}</a> : <span className="flex items-center gap-2 text-xs text-slate-600"><GitBranch className="size-3.5" />No repository linked</span>}</article>)}</div> : <p className="p-8 text-center text-sm text-slate-500">Your project history will appear here.</p>}
      </section>
      <section className="mt-6 rounded-2xl border border-line bg-panel/60 p-5 sm:p-6"><div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-xl bg-sky-400/10 text-sky-300"><Gauge className="size-5" /></span><div><h3 className="font-semibold text-white">Benchmark summary</h3><p className="mt-1 text-xs text-muted">Latest available AutoDev performance report</p></div></div>{benchmarks.isLoading ? <p className="mt-5 text-sm text-muted">Loading benchmark report…</p> : benchmarks.isError ? <p role="alert" className="mt-5 text-sm text-rose-300">Benchmark report is unavailable.</p> : benchmarks.data?.available ? <pre className="mt-5 max-h-80 overflow-auto rounded-xl border border-line bg-[#080c14] p-4 text-xs leading-5 text-slate-300">{JSON.stringify(benchmarks.data.report, null, 2)}</pre> : <p className="mt-5 rounded-xl border border-dashed border-line p-5 text-sm text-slate-500">No saved benchmark report is available yet. Run the existing benchmark command to generate one.</p>}</section>
    </div>
  );
}
