import axios from "axios";
import type {
  DashboardData,
  DailyReport,
  ExecutionState,
  GitHubStatus,
  LogEvent,
  ProjectCreatePayload,
  ProjectCreateResponse,
  ProjectSummary,
  RoadmapDay,
  SettingsData,
} from "../types";

const fallbackBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function readConfiguredBaseUrl(): string {
  try {
    const saved = localStorage.getItem("autodev-ui-settings");
    const configured = saved ? JSON.parse(saved)?.backend_url : undefined;
    if (typeof configured === "string" && configured.trim()) {
      const parsed = new URL(configured);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.origin;
    }
  } catch {
    return fallbackBaseUrl;
  }
  return fallbackBaseUrl;
}

export let apiBaseUrl = readConfiguredBaseUrl();
export const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
});

export function configureApiBaseUrl(value: string) {
  const parsed = new URL(value.trim());
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("Backend URL must use HTTP or HTTPS.");
  }
  apiBaseUrl = parsed.origin;
  api.defaults.baseURL = apiBaseUrl;
}

export const apiService = {
  health: async () => (await api.get<{ status: string }>("/health")).data,
  dashboard: async () => (await api.get<DashboardData>("/dashboard")).data,
  history: async () => (await api.get<ProjectSummary[]>("/project/history")).data,
  status: async () => (await api.get<ProjectSummary>("/project/status")).data,
  roadmap: async () =>
    (await api.get<{ project_id: string; days: RoadmapDay[] }>("/project/roadmap")).data,
  day: async (day: number) => (await api.get<RoadmapDay>(`/project/day/${day}`)).data,
  currentDay: async () => (await api.get<ExecutionState & { roadmap_day: RoadmapDay }>("/project/current-day")).data,
  currentMilestone: async () => (await api.get("/project/current-milestone")).data,
  commits: async () => (await api.get("/project/commits")).data,
  report: async (day?: number) =>
    (await api.get<DailyReport>("/project/report", { params: day ? { day } : {} })).data,
  logs: async (after = 0) =>
    (await api.get<LogEvent[]>("/project/logs", { params: { after, limit: 500 } })).data,
  createProject: async (payload: ProjectCreatePayload) =>
    (await api.post<ProjectCreateResponse>("/project/create", payload)).data,
  action: async (action: "start" | "pause" | "resume" | "stop", projectId?: string) =>
    (await api.post(`/project/${action}`, projectId ? { project_id: projectId } : {})).data,
  runDay: async (projectId?: string) =>
    (await api.post("/project/run-day", projectId ? { project_id: projectId } : {})).data,
  runMilestone: async (projectId?: string) =>
    (await api.post("/project/run-milestone", projectId ? { project_id: projectId } : {})).data,
  createCommit: async (projectId?: string) =>
    (await api.post("/project/create-commit", projectId ? { project_id: projectId } : {})).data,
  push: async (projectId?: string) =>
    (await api.post("/project/push", projectId ? { project_id: projectId } : {})).data,
  review: async (projectId?: string) =>
    (await api.post("/project/review", projectId ? { project_id: projectId } : {})).data,
  githubStatus: async () => (await api.get<GitHubStatus>("/github/status")).data,
  benchmarks: async () => (await api.get("/benchmarks")).data,
  metrics: async () => (await api.get("/metrics")).data,
  settings: async () => (await api.get<SettingsData>("/settings")).data,
};

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return "AutoDev API is unreachable. Check the backend connection.";
    const detail = error.response.data?.detail;
    return typeof detail === "string" ? detail : "The request could not be completed.";
  }
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}
