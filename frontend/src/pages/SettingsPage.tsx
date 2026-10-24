import { useEffect, useState } from "react";
import { Check, Github, Globe2, Settings2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiService, configureApiBaseUrl } from "../services/api";
import { PageHeading } from "../components/PageHeading";
import type { SettingsData } from "../types";

const localKey = "autodev-ui-settings";

export function SettingsPage() {
  const query = useQuery({ queryKey: ["settings"], queryFn: apiService.settings, retry: 1 });
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  useEffect(() => {
    if (!query.data) return;
    const local = localStorage.getItem(localKey);
    if (!local) {
      setSettings(query.data);
      return;
    }
    try {
      setSettings({ ...query.data, ...JSON.parse(local) });
    } catch {
      localStorage.removeItem(localKey);
      setSettings(query.data);
    }
  }, [query.data]);
  const update = <K extends keyof SettingsData>(key: K, value: SettingsData[K]) => {
    setSettings((current) => current ? { ...current, [key]: value } : current);
    setSaved(false);
    setSaveError("");
  };
  return (
    <div>
      <PageHeading title="Settings" subtitle="Set local dashboard defaults and repository preferences." />
      {query.isLoading ? <div className="h-80 animate-pulse rounded-2xl bg-panel" /> : query.isError ? <p role="alert" className="rounded-xl border border-rose-400/20 bg-rose-400/5 p-4 text-sm text-rose-300">Settings could not be loaded from the backend.</p> : settings && <div className="max-w-3xl rounded-2xl border border-line bg-panel/60 p-5 sm:p-7">
        <div className="mb-6 flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-xl bg-brand/10 text-brand"><Settings2 className="size-5" /></span><div><h2 className="font-semibold text-white">Workspace preferences</h2><p className="mt-1 text-xs text-muted">These preferences are stored in this browser.</p></div></div>
        <div className="space-y-5">
          <label className="field-wrap"><span><Github className="mr-1.5 inline size-3.5" />GitHub repository</span><input value={settings.github_repository} onChange={(event) => update("github_repository", event.target.value)} placeholder="https://github.com/you/project" /></label>
          <div className="grid gap-4 sm:grid-cols-2"><label className="field-wrap"><span>Default commit target</span><input type="number" min={1} max={8} value={settings.default_commit_target} onChange={(event) => update("default_commit_target", Number(event.target.value))} /></label><label className="field-wrap"><span>Default working hours</span><input type="number" min={1} max={24} value={settings.default_working_hours} onChange={(event) => update("default_working_hours", Number(event.target.value))} /></label></div>
          <label className="field-wrap"><span>Theme</span><select value={settings.theme} onChange={(event) => update("theme", event.target.value)}><option value="dark">Dark</option><option value="system">System (dark dashboard)</option></select></label>
          <label className="field-wrap"><span><Globe2 className="mr-1.5 inline size-3.5" />Backend URL</span><input value={settings.backend_url} onChange={(event) => update("backend_url", event.target.value)} /></label>
        </div>
        {saveError && <p role="alert" className="mt-4 text-sm text-rose-300">{saveError}</p>}
        <button className="button-primary mt-6" onClick={() => { try { configureApiBaseUrl(settings.backend_url); localStorage.setItem(localKey, JSON.stringify(settings)); setSaved(true); setSaveError(""); } catch (error) { setSaved(false); setSaveError(error instanceof Error ? error.message : "Preferences could not be saved."); } }}><Check className="size-4" />{saved ? "Saved locally" : "Save preferences"}</button>
      </div>}
    </div>
  );
}
