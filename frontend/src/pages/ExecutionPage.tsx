import { Activity, Clock3, Cpu, GitCommitHorizontal } from "lucide-react";
import { ExecutionControls } from "../components/ExecutionControls";
import { MetricCard } from "../components/MetricCard";
import { PageHeading } from "../components/PageHeading";
import { ProgressBar } from "../components/ProgressBar";
import { TerminalViewer } from "../components/TerminalViewer";
import { useProjectStatus } from "../hooks/useProject";

export function ExecutionPage() {
  const query = useProjectStatus();
  const project = query.data;
  return (
    <div>
      <PageHeading title="Execution" subtitle="Watch the daily engineering run and manage its lifecycle." action={<ExecutionControls project={project} />} />
      {query.isLoading ? <div className="h-40 animate-pulse rounded-2xl bg-panel" /> : query.isError ? <div role="alert" className="rounded-2xl border border-dashed border-line bg-panel/50 p-8 text-center"><Activity className="mx-auto size-6 text-slate-600" /><p className="mt-3 text-sm text-slate-300">No active project execution</p><p className="mt-1 text-xs text-muted">Create a project to start streaming execution logs.</p></div> : project && <>
        <section className="mb-5 rounded-2xl border border-line bg-panel/60 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-muted">Current project</p><h2 className="mt-2 text-xl font-semibold text-white">{project.project_name}</h2><p className="mt-1 text-sm text-muted">Day {project.current_day} of {project.total_days} · {project.status.replace("_", " ")}</p></div><div className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize ${project.status === "running" ? "bg-mint/10 text-mint" : "bg-surface text-slate-300"}`}>{project.status}</div></div>
          <div className="mt-6"><ProgressBar value={project.progress_percent} showLabel /></div>
          {(project.current_milestone || project.current_task) && <div className="mt-5 rounded-xl border border-line bg-surface/60 p-4"><p className="text-[11px] uppercase tracking-wider text-slate-500">Current milestone</p><p className="mt-1 text-sm text-slate-200">{project.current_milestone ?? project.current_task}</p></div>}
          {project.error && <div role="alert" className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/5 p-4 text-sm text-rose-300">{project.error}</div>}
        </section>
        <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Active day" value={`${project.current_day} / ${project.total_days}`} detail="Daily milestone" icon={Clock3} /><MetricCard label="Commits today" value={`${project.current_commit_number ?? project.commits_today} / ${project.daily_commit_target ?? 0}`} detail="Meaningful changes only" icon={GitCommitHorizontal} accent="mint" /><MetricCard label="Review status" value={project.review_status ?? "pending"} detail={`Push: ${project.push_status ?? "not configured"}`} icon={Cpu} accent="blue" /><MetricCard label="Elapsed time" value={formatElapsed(project.elapsed_seconds)} detail="Active execution time" icon={Clock3} accent="amber" /></div>
        {project.files_changed?.length ? <section className="mb-5 rounded-2xl border border-line bg-panel/60 p-5"><h2 className="text-sm font-semibold text-white">Files changed</h2><ul className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">{project.files_changed.map((file) => <li className="truncate font-mono" key={file}>{file}</li>)}</ul></section> : null}
        <TerminalViewer />
      </>}
    </div>
  );
}

function formatElapsed(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600).toString().padStart(2, "0");
  const minutes = Math.floor((total % 3600) / 60).toString().padStart(2, "0");
  const secs = (total % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
}
