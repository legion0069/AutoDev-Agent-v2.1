import { FolderKanban, Github, Plus } from "lucide-react";
import { ProjectForm } from "../components/ProjectForm";
import { PageHeading } from "../components/PageHeading";
import { useProjectHistory } from "../hooks/useProject";

export function ProjectsPage() {
  const history = useProjectHistory();
  return (
    <div>
      <PageHeading title="Projects" subtitle="Create a roadmap or return to a project already in progress." />
      <div className="grid items-start gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <ProjectForm />
        <section className="rounded-2xl border border-line bg-panel/60 p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between"><div><h3 className="font-semibold text-white">Your workspace</h3><p className="mt-1 text-xs text-muted">Recent and active projects</p></div><span className="rounded-lg bg-surface p-2 text-muted"><FolderKanban className="size-4" /></span></div>
          {history.isLoading ? <p className="py-8 text-center text-sm text-muted">Loading projects…</p> : history.isError ? <p role="alert" className="py-8 text-center text-sm text-rose-300">Projects could not be loaded. Retry in a moment.</p> : history.data?.length ? <div className="space-y-3">{history.data.map((project) => <article key={project.project_id} className="rounded-xl border border-line bg-surface/50 p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h4 className="truncate text-sm font-medium text-slate-100">{project.project_name}</h4><p className="mt-1 text-xs text-slate-500">Day {project.completed_days} of {project.total_days} · {project.status}</p></div><span className={`rounded-full px-2 py-1 text-[10px] capitalize ${project.status === "completed" ? "bg-emerald-400/10 text-mint" : "bg-violet-400/10 text-violet-200"}`}>{project.status}</span></div>{project.repository && <a href={project.repository} target="_blank" rel="noreferrer" className="mt-3 flex items-center gap-2 truncate text-xs text-slate-500 hover:text-violet-300"><Github className="size-3.5 shrink-0" />{project.repository}</a>}</article>)}</div> : <div className="py-8 text-center"><Plus className="mx-auto size-6 text-slate-600" /><p className="mt-3 text-sm text-slate-400">No projects yet</p><p className="mt-1 text-xs text-slate-600">Use the form to create your first roadmap.</p></div>}
        </section>
      </div>
    </div>
  );
}
