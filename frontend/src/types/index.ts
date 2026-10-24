export interface ProjectSummary {
  project_id: string;
  project_name: string;
  status: string;
  current_day: number;
  total_days: number;
  completed_days: number;
  progress_percent: number;
  remaining_days: number;
  commits_today: number;
  current_milestone?: string | null;
  current_commit_number?: number;
  files_changed?: string[];
  review_status?: string;
  push_status?: string;
  current_task: string | null;
  started_at: string | null;
  elapsed_seconds: number;
  updated_at: string;
  repository: string;
  error: string | null;
  description?: string;
  tech_stack?: string[];
  working_hours?: number;
  daily_commit_target?: number;
  mode?: "autonomous" | "approval";
  commits?: CommitInfo[];
}

export interface CommitInfo {
  hash?: string;
  message?: string;
  day?: number;
  milestone_id?: string;
  files?: string[];
  timestamp?: string;
}

export interface RoadmapDay {
  day: number;
  phase_name: string;
  goals: string[];
  tasks: string[];
  deliverables: string[];
  testing_focus: string;
  git_commit_message: string;
  status: "completed" | "in_progress" | "pending";
  completion: number;
  commits: CommitInfo[];
  tests: string[];
}

export interface LogEvent {
  event_id: number;
  timestamp: string;
  level: string;
  event: string;
  message: string;
  day: number | null;
  data: Record<string, unknown>;
}

export interface MilestoneInfo {
  milestone_id: string;
  title: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  error: string | null;
}

export interface ExecutionState {
  current_day: number;
  current_milestone: string | null;
  milestones: MilestoneInfo[];
  completed_milestones: string[];
  commit_count: number;
  completed_commits?: CommitInfo[];
  failed_tasks?: Array<{ milestone_id: string; error: string }>;
  retry_queue?: string[];
  duration_seconds?: number;
  status: string;
}

export interface DailyReport {
  day: number;
  path: string;
  content: string | null;
}

export interface DashboardData {
  current_project: ProjectSummary | null;
  execution_status: string;
  today_progress: number;
  remaining_days: number;
  commits_today: number;
  overall_progress: number;
  recent_activity: LogEvent[];
}

export interface ProjectCreatePayload {
  project_name: string;
  description: string;
  tech_stack: string[];
  days: number;
  working_hours: number;
  daily_commit_target: number;
  repository: string;
  mode: "autonomous" | "approval";
}

export interface ProjectCreateResponse {
  project: ProjectSummary & { plan: { phases: RoadmapDay[] } };
  roadmap: RoadmapDay[];
  daily_plan: RoadmapDay;
  progress: ProjectSummary;
  execution_metadata: Record<string, unknown>;
}

export interface SettingsData {
  github_repository: string;
  default_commit_target: number;
  default_working_hours: number;
  theme: string;
  backend_url: string;
}

export interface GitHubStatus {
  repository: string;
  configured: boolean;
  gh_cli_available: boolean;
  authenticated: boolean;
}
