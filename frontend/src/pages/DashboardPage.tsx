import { Activity, ArrowRight, Clock3, GitCommitHorizontal, Layers3, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../components/MetricCard";
import { PageHeading } from "../components/PageHeading";
import { ProgressBar } from "../components/ProgressBar";
import { useDashboard, useProjectStatus } from "../hooks/useProject";
import { ExecutionControls } from "../components/ExecutionControls";
import { apiService } from "../services/api";

export function DashboardPage() {
  const dashboard = useDashboard();
  const status = useProjectStatus();
  const github = useQuery({ queryKey: ["github-status"], queryFn: apiService.githubStatus, retry: 1 });
  const data = dashboard.data;
  const project = data?.current_project;
  if (dashboard.isLoading) return <LoadingState />;

  return (
    <div>
      <PageHeading title="Good work starts with a plan." subtitle="Your engineering command center for autonomous project delivery." action={<Link to="/projects" className="button-primary"><Sparkles className="size-4" />New project</Link>} />
      {dashboard.isError && <div role="alert" className="mb-5 rounded-xl border border-rose-400/20 bg-rose-400/5 p-4 text-sm text-rose-300">Dashboard data is unavailable. Check the backend connection and retry.</div>}
      {project ? (
        <section className="relative overflow-hidden rounded-3xl border border-violet-300/15 bg-gradient-to-br from-[#1b1c37] via-[#131a2c] to-panel p-6 shadow-glow sm:p-8">
          <div className="pointer-events-none absolute -right-16 -top-32 size-80 rounded-full bg-brand/10 blur-3xl" />
          <div className="relative flex flex-wrap items-start justify-between gap-6">
            <div className="max-w-2xl">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-violet-300/15 bg-violet-300/[0.06] px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-violet-200"><span className="size-1.5 rounded-full bg-mint" />Current project</div>
              <h2 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">{project.project_name}</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">{project.description || "Your project roadmap and engineering progress at a glance."}</p>
              <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-400">
                <span className="flex items-center gap-2"><Activity className="size-4 text-violet-300" />{project.status.replace("_", " ")}</span>
                <span className="flex items-center gap-2"><Clock3 className="size-4 text-violet-300" />Day {project.current_day} of {project.total_days}</span>
                {project.repository && <a href={project.repository} target="_blank" rel="noreferrer" className="max-w-xs truncate text-violet-200 hover:underline">{project.repository}</a>}
              </div>
              <div className="mt-7 max-w-xl"><ProgressBar value={project.progress_percent} showLabel /></div>
              <div className="mt-6"><ExecutionControls project={status.data ?? project} /></div>
            </div>
            <div className="relative flex size-32 items-center justify-center sm:size-40">
              <div className="absolute inset-0 rounded-full border-[7px] border-white/[0.04]" />
              <div className="absolute inset-0 rounded-full border-[7px] border-transparent border-t-brand border-r-violet-300" style={{ transform: `rotate(${Math.min(project.progress_percent, 100) * 3.6}deg)` }} />
              <div className="text-center"><span className="block text-3xl font-semibold text-white">{project.progress_percent}%</span><span className="text-[10px] uppercase tracking-widest text-muted">complete</span></div>
            </div>
          </div>
        </section>
      ) : (
        <section className="rounded-3xl border border-dashed border-line bg-panel/40 px-6 py-12 text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-brand/10 text-brand"><Sparkles className="size-6" /></span>
          <h2 className="mt-4 text-lg font-semibold text-white">Your next project starts here</h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">Create a project to generate a roadmap, connect your repository, and follow daily engineering work.</p>
          <Link to="/projects" className="button-primary mt-5 inline-flex">Create project <ArrowRight className="size-4" /></Link>
        </section>
      )}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Today's progress" value={`${data?.today_progress ?? 0}%`} detail="Current daily milestone" icon={Activity} accent="violet" />
        <MetricCard label="Remaining days" value={data?.remaining_days ?? 0} detail="On the active roadmap" icon={Clock3} accent="blue" />
        <MetricCard label="Commits today" value={data?.commits_today ?? 0} detail="Meaningful work captured" icon={GitCommitHorizontal} accent="mint" />
        <MetricCard label="Project health" value={project?.status ?? "Ready"} detail={project?.repository ? "Repository connected" : "No repository configured"} icon={Layers3} accent="amber" />
      </div>
      {project && <section className="mt-5 grid gap-4 rounded-2xl border border-line bg-panel/60 p-5 sm:grid-cols-2 xl:grid-cols-4">
        <div><p className="text-[11px] uppercase tracking-wider text-muted">Current milestone</p><p className="mt-2 truncate text-sm font-medium text-slate-200">{project.current_milestone ?? project.current_task ?? "Waiting for execution"}</p></div>
        <div><p className="text-[11px] uppercase tracking-wider text-muted">Execution timer</p><p className="mt-2 text-sm font-medium text-slate-200">{formatElapsed(status.data?.elapsed_seconds ?? project.elapsed_seconds)}</p></div>
        <div><p className="text-[11px] uppercase tracking-wider text-muted">Current commit</p><p className="mt-2 text-sm font-medium text-slate-200">{project.current_commit_number ?? project.commits_today} / {project.daily_commit_target ?? 0} today</p></div>
        <div><p className="text-[11px] uppercase tracking-wider text-muted">Review / push</p><p className="mt-2 text-sm font-medium text-slate-200">{project.review_status ?? "pending"} / {project.push_status ?? "not configured"}</p></div>
        {project.current_task && <div className="sm:col-span-2 xl:col-span-4"><p className="text-[11px] uppercase tracking-wider text-muted">Current task</p><p className="mt-2 truncate text-sm text-slate-300">{project.current_task}</p></div>}
        {project.files_changed?.length ? <div className="sm:col-span-2 xl:col-span-4"><p className="text-[11px] uppercase tracking-wider text-muted">Files changed</p><p className="mt-2 truncate font-mono text-xs text-slate-400">{project.files_changed.join(" · ")}</p></div> : null}
      </section>}
      <div className="mt-7 grid gap-5 xl:grid-cols-[1.4fr_0.8fr]">
        <section className="rounded-2xl border border-line bg-panel/60 p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between"><div><h3 className="font-semibold text-white">Recent activity</h3><p className="mt-1 text-xs text-muted">Latest events from the execution stream</p></div><Link to="/execution" className="text-xs font-medium text-violet-300 hover:text-violet-200">View execution <ArrowRight className="ml-1 inline size-3.5" /></Link></div>
          <div className="space-y-1">
            {(data?.recent_activity ?? []).length ? data!.recent_activity.map((item) => <div key={item.event_id} className="flex gap-4 border-t border-line/60 py-3 first:border-0"><span className="mt-1.5 size-2 shrink-0 rounded-full bg-violet-300" /><div className="min-w-0 flex-1"><p className="truncate text-sm text-slate-300">{item.message}</p><p className="mt-1 text-[11px] text-slate-600">{new Date(item.timestamp).toLocaleString()}</p></div></div>) : <p className="py-7 text-center text-sm text-slate-600">No activity yet. Start a project to see updates.</p>}
          </div>
        </section>
        <section className="rounded-2xl border border-line bg-panel/60 p-5 sm:p-6">
          <div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-xl bg-emerald-400/10 text-mint"><GitCommitHorizontal className="size-5" /></span><div><h3 className="font-semibold text-white">GitHub connection</h3><p className="text-xs text-muted">Repository and contribution status</p></div></div>
          <div className="mt-5 rounded-xl border border-line bg-surface/70 p-4">
            <p className="text-xs text-muted">Connected repository</p>
            <p className="mt-2 truncate text-sm text-slate-200">{github.data?.repository || project?.repository || "No repository linked"}</p>
            <p className={`mt-3 text-xs ${github.data?.authenticated ? "text-mint" : "text-amber-300"}`}>
              {github.isLoading ? "Checking GitHub status…" : github.isError ? "GitHub status is unavailable" : github.data?.authenticated ? "GitHub CLI authenticated" : github.data?.gh_cli_available ? "GitHub CLI is not authenticated" : "GitHub CLI is not installed"}
            </p>
            {project && <p className="mt-2 text-xs text-slate-400">Latest push: {project.push_status ?? "not configured"}</p>}
            <p className="mt-2 text-[11px] text-slate-500">Push access depends on your local Git and GitHub CLI configuration.</p>
          </div>
          <Link to="/settings" className="mt-4 inline-flex items-center text-xs font-medium text-violet-300">Configure settings <ArrowRight className="ml-1 size-3.5" /></Link>
        </section>
      </div>
    </div>
  );
}

function formatElapsed(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600).toString().padStart(2, "0");
  const minutes = Math.floor((total % 3600) / 60).toString().padStart(2, "0");
  return `${hours}:${minutes.toString().padStart(2, "0")}`;
}

function LoadingState() {
  return <div className="animate-pulse space-y-5"><div className="h-8 w-56 rounded bg-panel" /><div className="h-64 rounded-3xl bg-panel" /><div className="grid gap-4 sm:grid-cols-4">{[1, 2, 3, 4].map((item) => <div key={item} className="h-28 rounded-2xl bg-panel" />)}</div></div>;
}
