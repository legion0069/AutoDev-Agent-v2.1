import { useState } from "react";
import { ArrowUpRight, LoaderCircle, Plus, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiService, errorMessage } from "../services/api";
import { useNotifications } from "./Notifications";
import type { ProjectCreatePayload } from "../types";

const initial: ProjectCreatePayload = {
  project_name: "",
  description: "",
  tech_stack: ["React", "FastAPI"],
  days: 30,
  working_hours: 3,
  daily_commit_target: 4,
  repository: "",
  mode: "autonomous",
};

function projectDefaults(): ProjectCreatePayload {
  try {
    const saved = localStorage.getItem("autodev-ui-settings");
    if (!saved) return initial;
    const settings = JSON.parse(saved);
    return {
      ...initial,
      repository: typeof settings.github_repository === "string" ? settings.github_repository : initial.repository,
      daily_commit_target: Number(settings.default_commit_target) || initial.daily_commit_target,
      working_hours: Number(settings.default_working_hours) || initial.working_hours,
    };
  } catch {
    return initial;
  }
}

export function ProjectForm() {
  const [form, setForm] = useState(projectDefaults);
  const [stackInput, setStackInput] = useState("");
  const [error, setError] = useState("");
  const queryClient = useQueryClient();
  const { notify } = useNotifications();
  const mutation = useMutation({
    mutationFn: async (payload: ProjectCreatePayload) => {
      const created = await apiService.createProject(payload);
      await apiService.action("start", created.project.project_id);
      return created;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      setError("");
      notify("Project created. Today's execution is starting.");
      setForm(initial);
    },
    onError: async (cause) => {
      setError(errorMessage(cause));
      await queryClient.invalidateQueries();
    },
  });
  const update = <K extends keyof ProjectCreatePayload>(key: K, value: ProjectCreatePayload[K]) =>
    setForm((current) => ({ ...current, [key]: value }));
  const addStackItem = () => {
    const item = stackInput.trim();
    if (item && !form.tech_stack.includes(item)) update("tech_stack", [...form.tech_stack, item]);
    setStackInput("");
  };

  return (
    <form
      className="rounded-2xl border border-line bg-panel/70 p-5 sm:p-6"
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate({ ...form, tech_stack: form.tech_stack.filter(Boolean) });
      }}
    >
      <div className="mb-6 flex items-center justify-between">
        <div><p className="text-sm font-semibold text-white">Create a project</p><p className="mt-1 text-xs text-muted">Describe the outcome. AutoDev will generate the day-by-day roadmap.</p></div>
        <span className="flex size-9 items-center justify-center rounded-xl bg-brand/10 text-brand"><Plus className="size-5" /></span>
      </div>
      {error && <div role="alert" className="mb-4 rounded-lg border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-300">{error}</div>}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="field-wrap sm:col-span-2"><span>Project name</span><input required minLength={1} maxLength={120} value={form.project_name} onChange={(e) => update("project_name", e.target.value)} placeholder="e.g. Student Productivity App" /></label>
        <label className="field-wrap sm:col-span-2"><span>Description</span><textarea required rows={3} value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="What should AutoDev build?" /></label>
        <div className="field-wrap sm:col-span-2"><span>Technology stack</span><div className="flex gap-2"><input value={stackInput} onChange={(e) => setStackInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addStackItem(); } }} placeholder="Add a technology" /><button type="button" onClick={addStackItem} className="button-secondary shrink-0">Add</button></div><div className="mt-2 flex flex-wrap gap-2">{form.tech_stack.map((item) => <button type="button" key={item} onClick={() => update("tech_stack", form.tech_stack.filter((value) => value !== item))} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-slate-300">{item}<X className="size-3" /></button>)}</div></div>
        <label className="field-wrap"><span>Duration · days</span><input type="number" min={1} max={365} value={form.days} onChange={(e) => update("days", Number(e.target.value))} /></label>
        <label className="field-wrap"><span>Working hours / day</span><input type="number" min={1} max={24} value={form.working_hours} onChange={(e) => update("working_hours", Number(e.target.value))} /></label>
        <label className="field-wrap"><span>Daily commit target</span><input type="number" min={1} max={8} value={form.daily_commit_target} onChange={(e) => update("daily_commit_target", Number(e.target.value))} /></label>
        <label className="field-wrap"><span>Execution mode</span><select value={form.mode} onChange={(e) => update("mode", e.target.value as ProjectCreatePayload["mode"])}><option value="autonomous">Autonomous</option><option value="approval">Approval</option></select></label>
        <label className="field-wrap sm:col-span-2"><span>GitHub repository <em className="not-italic text-slate-600">optional</em></span><input type="text" value={form.repository} onChange={(e) => update("repository", e.target.value)} placeholder="https://github.com/you/project" /></label>
      </div>
      <button disabled={mutation.isPending || form.tech_stack.length === 0} className="button-primary mt-6 w-full justify-center sm:w-auto">
        {mutation.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowUpRight className="size-4" />}Create & run
      </button>
    </form>
  );
}
