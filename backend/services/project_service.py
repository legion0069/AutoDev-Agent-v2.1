"""Application service connecting the web API to existing AutoDev workflows."""

from __future__ import annotations

import asyncio
import ast
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, time as local_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from agents.git_agent import CommitResult, GitAgent
from agents.planner_agent import generate_project_plan, save_project_plan
from agents.task_planner_agent import Task, TaskPlannerAgent
from backend.schemas.project import ProjectCreateRequest, ProjectScheduleRequest
from core.commit_scheduler import CommitScheduler
from core.day_execution_engine import DayExecutionEngine, Milestone, milestone_slug
from core.github_execution import GitHubExecution

logger = logging.getLogger("AutoDev.WebUI")


class _OrchestratorLogHandler(logging.Handler):
    def __init__(self, service: "ProjectService", day: int) -> None:
        super().__init__()
        self.service = service
        self.day = day

    def emit(self, record: logging.LogRecord) -> None:
        self.service.publish_log(
            self.format(record),
            level=record.levelname.lower(),
            event="execution.log",
            day=self.day,
        )


class _MilestoneGitAgent(GitAgent):
    """Disables Orchestrator's implicit commit; V5.2 commits after validation."""

    def commit(self, **kwargs: Any) -> CommitResult:
        return CommitResult(
            success=False,
            error="Commit is managed by the V5.2 commit scheduler.",
            message="Commit deferred until milestone validation is complete.",
        )


class _MilestonePlanner(TaskPlannerAgent):
    """Adapts one persisted roadmap milestone into exactly one orchestrator task."""

    def __init__(self, milestone: Milestone, output_path: Path) -> None:
        super().__init__(output_path=output_path)
        self.milestone = milestone

    def execute(self, context: dict[str, Any]) -> list[Task]:
        return [
            Task(
                id=self.milestone.milestone_id,
                title=self.milestone.title,
                description=self.milestone.description or self.milestone.title,
                priority=1,
            )
        ]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectService:
    """Persists project records, streams logs, and delegates daily work to Orchestrator."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        execution_runner: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        default_data_dir = Path(
            os.environ.get("AUTODEV_DATA_DIR", Path.home() / ".autodev")
        )
        self.data_dir = Path(data_dir or default_data_dir).expanduser().resolve() / "web-ui"
        self.projects_dir = self.data_dir / "projects"
        self.workspaces_dir = self.data_dir / "workspaces"
        self.state_path = self.data_dir / "state.json"
        self.execution_runner = execution_runner
        self._lock = threading.RLock()
        self._projects: dict[str, dict[str, Any]] = {}
        self._logs: list[dict[str, Any]] = []
        self._listeners: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = set()
        self._threads: dict[str, threading.Thread] = {}
        self._run_started: dict[str, float] = {}
        self._interrupted_project_ids: list[str] = []
        self._next_event_id = 1
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._load()

    def create_project(self, request: ProjectCreateRequest) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        plan = generate_project_plan(
            project_name=request.project_name,
            project_description=request.description,
            tech_stack=", ".join(request.tech_stack),
            days=request.days,
        )
        plan["github_repository"] = request.repository
        plan["execution_mode"] = request.mode
        plan["working_hours"] = request.working_hours
        plan["daily_commit_target"] = request.daily_commit_target
        plan["schedule"] = {
            "enabled": request.schedule_enabled,
            "time": request.schedule_time,
            "timezone": request.timezone,
        }
        for daily_commit_plan in plan["daily_commit_plan"]:
            daily_commit_plan["expected_commits"] = str(request.daily_commit_target)
        plan["project_state"].update(
            {
                "project_id": project_id,
                "status": "planned",
                "repository": request.repository,
                "execution_mode": request.mode,
            }
        )

        record = {
            "project_id": project_id,
            "project_name": request.project_name,
            "description": request.description,
            "tech_stack": request.tech_stack,
            "days": request.days,
            "working_hours": request.working_hours,
            "daily_commit_target": request.daily_commit_target,
            "repository": request.repository,
            "mode": request.mode,
            "plan": plan,
            "status": "planned",
            "current_day": 1,
            "completed_days": [],
            "day_results": {},
            "commits": [],
            "current_task": None,
            "started_at": None,
            "updated_at": _timestamp(),
            "error": None,
            "pause_requested": False,
            "stop_requested": False,
            "elapsed_seconds": 0.0,
            "current_milestone": None,
            "current_commit_number": 0,
            "files_changed": [],
            "review_status": "pending",
            "push_status": "not_configured",
            "execution_started_at": None,
            "schedule_enabled": request.schedule_enabled,
            "schedule_time": request.schedule_time,
            "timezone": request.timezone,
            "last_run_at": None,
            "last_run_local_date": None,
        }

        with self._lock:
            self._projects[project_id] = record
            self._active_project_id = project_id
            self._persist()
        self.projects_dir.joinpath(project_id, "memory").mkdir(parents=True, exist_ok=True)
        save_project_plan(
            plan,
            self.projects_dir / project_id / "memory" / "project_plan.json",
        )
        self.publish_log(
            "Project roadmap generated.",
            event="planning.completed",
            day=1,
            data={"project_id": project_id, "days": request.days},
        )
        return self.get_project(project_id)

    def get_project(self, project_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            resolved_id = project_id or getattr(self, "_active_project_id", None)
            if resolved_id is None or resolved_id not in self._projects:
                raise KeyError("No project is available. Create a project first.")
            return json.loads(json.dumps(self._projects[resolved_id]))

    def get_status(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        completed_days = len(project["completed_days"])
        total_days = project["days"]
        progress = min(100.0, completed_days / total_days * 100.0)
        at_day_boundary = project["status"] in {"waiting", "completed"} or (
            project["status"] in {"paused", "stopped"} and project.get("pause_at_boundary", False)
        )
        commit_day = (
            project["current_day"] - 1
            if at_day_boundary and completed_days
            else project["current_day"]
        )
        with self._lock:
            running_for = (
                max(0.0, time.monotonic() - self._run_started[project["project_id"]])
                if project["project_id"] in self._run_started
                and project["status"] == "running"
                else 0.0
            )
        return {
            "project_id": project["project_id"],
            "project_name": project["project_name"],
            "status": project["status"],
            "current_day": project["current_day"],
            "total_days": total_days,
            "completed_days": completed_days,
            "progress_percent": round(progress, 1),
            "remaining_days": max(0, total_days - completed_days),
            "commits_today": sum(
                1 for commit in project["commits"]
                if commit.get("day") == commit_day
            ),
            "current_milestone": project.get("current_milestone"),
            "current_commit_number": sum(
                1 for commit in project["commits"] if commit.get("day") == commit_day
            ),
            "files_changed": project.get("files_changed", []),
            "review_status": project.get("review_status", "pending"),
            "push_status": project.get("push_status", "not_configured"),
            "current_task": project["current_task"],
            "started_at": project["started_at"],
            "elapsed_seconds": round(project.get("elapsed_seconds", 0.0) + running_for, 1),
            "updated_at": project["updated_at"],
            "repository": project["repository"],
            "error": project["error"],
            "schedule_enabled": project.get("schedule_enabled", False),
            "schedule_time": project.get("schedule_time", "09:00"),
            "timezone": project.get("timezone", "UTC"),
            "next_run_at": self._next_run_at(project),
            "last_run_at": project.get("last_run_at"),
        }

    def start(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        with self._lock:
            record = self._projects[project["project_id"]]
            if record["status"] == "running":
                raise RuntimeError("This project is already running.")
            if record["status"] == "completed":
                raise RuntimeError("This project has completed all planned days.")
            record["status"] = "running"
            record["error"] = None
            record["pause_requested"] = False
            record["stop_requested"] = False
            record["pause_at_boundary"] = False
            record["started_at"] = record["started_at"] or _timestamp()
            local_now = datetime.now(ZoneInfo(record.get("timezone", "UTC")))
            record["last_run_local_date"] = local_now.date().isoformat()
            record["last_run_at"] = _timestamp()
            self._run_started[record["project_id"]] = time.monotonic()
            phase = record["plan"]["phases"][record["current_day"] - 1]
            record["current_task"] = (phase.get("tasks") or [phase["phase_name"]])[0]
            record["updated_at"] = _timestamp()
            self._persist()
            thread = threading.Thread(
                target=self._run_daily,
                args=(record["project_id"],),
                name=f"autodev-project-{record['project_id'][:8]}",
                daemon=True,
            )
            self._threads[record["project_id"]] = thread
        self.publish_log("Starting today's execution.", event="execution.started", day=project["current_day"])
        self.publish_log("Autonomous project execution started.", event="execution_started", day=project["current_day"])
        thread.start()
        return self.get_status(project["project_id"])

    def update_schedule(
        self, payload: ProjectScheduleRequest, project_id: str | None = None
    ) -> dict[str, Any]:
        project = self.get_project(project_id)
        with self._lock:
            record = self._projects[project["project_id"]]
            if payload.enabled and record["status"] in {"completed", "paused", "stopped"}:
                raise RuntimeError(
                    f"A project in {record['status']!r} status cannot be scheduled."
                )
            record["schedule_enabled"] = payload.enabled
            record["schedule_time"] = payload.schedule_time
            record["timezone"] = payload.timezone
            record["updated_at"] = _timestamp()
            self._persist()
        self.publish_log(
            "Daily schedule enabled." if payload.enabled else "Daily schedule paused.",
            event="schedule.updated",
            day=project["current_day"],
            data={
                "enabled": payload.enabled,
                "schedule_time": payload.schedule_time,
                "timezone": payload.timezone,
            },
        )
        return self.get_status(project["project_id"])

    def run_due_schedules(self, now: datetime | None = None) -> list[str]:
        """Starts each due project at most once per local calendar day."""
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Scheduler time must be timezone-aware.")
        with self._lock:
            projects = [
                json.loads(json.dumps(project))
                for project in self._projects.values()
            ]
        started: list[str] = []
        for project in projects:
            if (
                not project.get("schedule_enabled", False)
                or project.get("status") not in {"planned", "waiting", "failed"}
            ):
                continue
            local_now = current.astimezone(ZoneInfo(project.get("timezone", "UTC")))
            if local_now.strftime("%H:%M") < project.get("schedule_time", "09:00"):
                continue
            if project.get("last_run_local_date") == local_now.date().isoformat():
                continue
            try:
                self.start(project["project_id"])
                started.append(project["project_id"])
            except RuntimeError:
                logger.info(
                    "Skipped scheduled start for project %s because its state changed.",
                    project["project_id"],
                )
        return started

    def start_scheduler(self, interval_seconds: float = 15.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("Scheduler interval must be positive.")
        with self._lock:
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                return
            self._scheduler_stop.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                args=(interval_seconds,),
                name="autodev-daily-scheduler",
                daemon=True,
            )
            self._scheduler_thread.start()

    def stop_scheduler(self, timeout: float = 5.0) -> None:
        self._scheduler_stop.set()
        thread = self._scheduler_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

    def _scheduler_loop(self, interval_seconds: float) -> None:
        while not self._scheduler_stop.wait(interval_seconds):
            try:
                self.run_due_schedules()
            except Exception:
                logger.exception("Daily scheduler iteration failed.")

    @staticmethod
    def _next_run_at(project: dict[str, Any]) -> str | None:
        if (
            not project.get("schedule_enabled", False)
            or project.get("status") in {"completed", "paused", "stopped"}
        ):
            return None
        zone = ZoneInfo(project.get("timezone", "UTC"))
        now = datetime.now(zone)
        scheduled = local_time.fromisoformat(project.get("schedule_time", "09:00"))
        run_date = now.date()
        if project.get("last_run_local_date") == run_date.isoformat():
            run_date += timedelta(days=1)
        scheduled_at = datetime.combine(run_date, scheduled, tzinfo=zone)
        if scheduled_at < now:
            scheduled_at = now
        return scheduled_at.astimezone(timezone.utc).isoformat(timespec="seconds")

    def resume_interrupted(self) -> list[dict[str, Any]]:
        """Restarts projects that were persisted as running when the service stopped."""
        interrupted = list(self._interrupted_project_ids)
        self._interrupted_project_ids.clear()
        return [self.start(project_id) for project_id in interrupted]

    def pause(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        with self._lock:
            record = self._projects[project["project_id"]]
            if record["status"] != "running":
                raise RuntimeError("Only a running project can be paused.")
            record["pause_requested"] = True
            record["schedule_enabled"] = False
            record["updated_at"] = _timestamp()
            self._persist()
        self.publish_log(
            "Pause requested; the active daily run will finish before pausing.",
            event="execution.pause_requested",
            day=project["current_day"],
        )
        return self.get_status(project["project_id"])

    def resume(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        if project["status"] not in {"paused", "stopped", "waiting", "planned", "failed"}:
            raise RuntimeError(f"Cannot resume a project in {project['status']!r} status.")
        return self.start(project["project_id"])

    def stop(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        with self._lock:
            record = self._projects[project["project_id"]]
            if record["status"] == "running":
                record["stop_requested"] = True
            elif record["status"] not in {"completed", "stopped"}:
                record["status"] = "stopped"
            record["schedule_enabled"] = False
            record["updated_at"] = _timestamp()
            self._persist()
        self.publish_log(
            "Stop requested; the active daily run will finish before stopping."
            if project["status"] == "running"
            else "Project stopped.",
            event="execution.stop_requested",
            day=project["current_day"],
        )
        return self.get_status(project["project_id"])

    def get_roadmap(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        completed = set(project["completed_days"])
        roadmap = []
        for phase in project["plan"]["phases"]:
            day = int(phase["day"])
            execution = DayExecutionEngine(self._execution_state_path(project["project_id"], day)).state
            total_milestones = len(execution.milestones) if execution else 0
            completed_milestones = len(execution.completed_milestones) if execution else 0
            day_status = (
                "completed"
                if day in completed
                else "in_progress"
                if day == project["current_day"] and project["status"] in {"running", "paused", "failed", "stopped"}
                else "pending"
            )
            roadmap.append(
                {
                    **phase,
                    "status": day_status,
                    "completion": 100 if day in completed else (
                        round(completed_milestones / total_milestones * 100)
                        if total_milestones else 0
                    ),
                    "commits": [
                        item for item in project["commits"] if item.get("day") == day
                    ],
                    "tests": self._day_tests(project.get("day_results", {}).get(str(day))),
                }
            )
        return {"project_id": project["project_id"], "days": roadmap}

    def get_day(self, day: int, project_id: str | None = None) -> dict[str, Any]:
        roadmap = self.get_roadmap(project_id)
        if day < 1 or day > len(roadmap["days"]):
            raise KeyError(f"Day {day} is outside the project roadmap.")
        return roadmap["days"][day - 1]

    def get_execution_state(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        day = project["current_day"]
        if day > project["days"]:
            day = project["days"]
        state_path = self._execution_state_path(project["project_id"], day)
        engine = DayExecutionEngine(state_path)
        state = engine.state
        if state is None:
            return {
                "current_day": day,
                "current_milestone": None,
                "milestones": [],
                "completed_milestones": [],
                "commit_count": 0,
                "status": "pending",
            }
        return {
            "current_day": state.current_day,
            "current_milestone": state.current_milestone,
            "milestones": [vars(item) for item in state.milestones],
            "completed_milestones": state.completed_milestones,
            "commit_count": state.commit_count,
            "completed_commits": state.completed_commits,
            "failed_tasks": state.failed_tasks,
            "retry_queue": state.retry_queue,
            "duration_seconds": state.duration_seconds,
            "status": state.status,
        }

    def run_day(self, project_id: str | None = None) -> dict[str, Any]:
        return self.start(project_id)

    def run_milestone(self, project_id: str | None = None) -> dict[str, Any]:
        return self.start(project_id)

    def create_commit(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        workspace = self.workspaces_dir / project["project_id"]
        if not workspace.is_dir():
            raise RuntimeError("The project workspace is not available.")
        scheduler = CommitScheduler(GitAgent(project_root=workspace))
        commit = scheduler.create_commit(
            project["current_day"],
            project.get("current_milestone") or "Manual milestone",
        )
        if commit is None:
            return {"success": False, "message": "No meaningful changes are available to commit."}
        record = {
            "hash": commit.commit_hash,
            "message": commit.commit_message,
            "day": project["current_day"],
            "timestamp": _timestamp(),
            "files": commit.files_committed,
        }
        with self._lock:
            self._projects[project["project_id"]]["commits"].append(record)
            self._persist()
        return {"success": True, "commit": record}

    def push(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        workspace = self.workspaces_dir / project["project_id"]
        commits = [item for item in project["commits"] if item.get("hash")]
        if not commits:
            raise RuntimeError("There are no project commits to push.")
        result = GitHubExecution(GitAgent(project_root=workspace)).push_and_verify(commits[-1]["hash"])
        with self._lock:
            self._projects[project["project_id"]]["push_status"] = "verified"
            self._persist()
        return result

    def review(self, project_id: str | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        state = self.get_execution_state(project["project_id"])
        return {
            "status": project.get("review_status", "pending"),
            "current_milestone": state.get("current_milestone"),
            "message": "Review is performed as part of each milestone execution.",
        }

    def get_commits(self, project_id: str | None = None) -> list[dict[str, Any]]:
        return self.get_project(project_id)["commits"]

    def get_report(self, project_id: str | None = None, day: int | None = None) -> dict[str, Any]:
        project = self.get_project(project_id)
        report_day = day or max(1, project["current_day"] - (project["status"] == "completed"))
        path = self.projects_dir / project["project_id"] / "memory" / "reports" / f"day_{report_day}.md"
        return {
            "day": report_day,
            "path": str(path),
            "content": path.read_text(encoding="utf-8") if path.is_file() else None,
        }

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._summary(project)
                for project in sorted(
                    self._projects.values(),
                    key=lambda item: item["updated_at"],
                    reverse=True,
                )
            ]

    def get_logs(self, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            return [
                event.copy()
                for event in self._logs
                if event["event_id"] > after
            ][:limit]

    def publish_log(
        self,
        message: str,
        *,
        level: str = "info",
        event: str = "log",
        day: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            log_event = {
                "event_id": self._next_event_id,
                "timestamp": _timestamp(),
                "level": level,
                "event": event,
                "message": message,
                "day": day,
                "data": data or {},
            }
            self._next_event_id += 1
            self._logs.append(log_event)
            self._persist()
            for loop, queue in tuple(self._listeners):
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, log_event)
                except RuntimeError:
                    self._listeners.discard((loop, queue))
                    logger.debug("Skipping closed WebSocket event loop.")
        return log_event

    def subscribe(self) -> tuple[asyncio.Queue[dict[str, Any]], Callable[[], None]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        listener = (loop, queue)
        with self._lock:
            self._listeners.add(listener)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.discard(listener)

        return queue, unsubscribe

    def dashboard(self) -> dict[str, Any]:
        with self._lock:
            projects = list(self._projects.values())
            active = next(
                (project for project in projects if project["project_id"] == getattr(self, "_active_project_id", None)),
                None,
            )
        if active is None:
            return {
                "current_project": None,
                "execution_status": "idle",
                "today_progress": 0,
                "remaining_days": 0,
                "commits_today": 0,
                "overall_progress": 0,
                "recent_activity": self.get_logs(limit=8),
            }
        execution = self.get_execution_state(active["project_id"])
        milestones = execution.get("milestones", [])
        today_progress = (
            round(len(execution.get("completed_milestones", [])) / len(milestones) * 100)
            if milestones
            else 100 if active["status"] == "completed" else 0
        )
        return {
            "current_project": self._summary(active),
            "execution_status": active["status"],
            "today_progress": today_progress,
            "remaining_days": self.get_status(active["project_id"])["remaining_days"],
            "commits_today": self.get_status(active["project_id"])["commits_today"],
            "overall_progress": self.get_status(active["project_id"])["progress_percent"],
            "recent_activity": self.get_logs(limit=8),
        }

    def metrics(self) -> dict[str, Any]:
        history = self.get_history()
        with self._lock:
            commit_count = sum(len(project["commits"]) for project in self._projects.values())
        return {
            "project_count": len(history),
            "completed_projects": sum(item["status"] == "completed" for item in history),
            "active_projects": sum(item["status"] == "running" for item in history),
            "commits": commit_count,
        }

    def settings(self) -> dict[str, Any]:
        try:
            project = self.get_project()
        except KeyError:
            project = None
        return {
            "github_repository": project["repository"] if project else "",
            "default_commit_target": project["daily_commit_target"] if project else 4,
            "default_working_hours": project["working_hours"] if project else 3,
            "theme": "dark",
            "backend_url": os.environ.get("AUTODEV_API_URL", "http://localhost:8000"),
            "schedule_enabled": project.get("schedule_enabled", False) if project else False,
            "schedule_time": project.get("schedule_time", "09:00") if project else "09:00",
            "timezone": project.get("timezone", "UTC") if project else "UTC",
        }

    def github_status(self) -> dict[str, Any]:
        project = None
        try:
            project = self.get_project()
        except KeyError:
            pass
        try:
            gh_available = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ) if _command_available("gh") else None
        except subprocess.TimeoutExpired:
            gh_available = None
        return {
            "repository": project["repository"] if project else "",
            "configured": bool(project and project["repository"]),
            "gh_cli_available": gh_available is not None,
            "authenticated": bool(gh_available and gh_available.returncode == 0),
        }

    def benchmarks(self) -> dict[str, Any]:
        report_path = Path(__file__).resolve().parents[2] / "memory" / "benchmarks" / "performance_report.json"
        if report_path.is_file():
            try:
                data = json.loads(report_path.read_text(encoding="utf-8"))
                return {"available": True, "report": data}
            except (OSError, ValueError) as exc:
                logger.warning("Could not read benchmark report %s: %s", report_path, exc)
                return {"available": False, "error": "The stored benchmark report could not be read."}
        return {"available": False, "report": None}

    def _run_daily(self, project_id: str) -> None:
        with self._lock:
            started = self._run_started.get(project_id, time.monotonic())
        try:
            while True:
                project = self.get_project(project_id)
                day = project["current_day"]
                self.publish_log("Generating today's tasks...", event="planning.started", day=day)
                if self.execution_runner is not None:
                    # Preserve the V5.1 injected runner's one-day execution contract.
                    result = self.execution_runner(project)
                    summary = self._normalize_execution_result(result)
                else:
                    recovered = self._completed_day_summary(project, day)
                    if recovered is not None:
                        summary = recovered
                        self.publish_log(
                            f"Recovered completed Day {day} without rerunning its milestones.",
                            event="execution.recovered",
                            day=day,
                        )
                    else:
                        summary = self._normalize_execution_result(
                            self._execute_orchestrator(project)
                        )

                with self._lock:
                    record = self._projects[project_id]
                    if summary.get("overall_success", True):
                        if summary.get("paused"):
                            record["status"] = "stopped" if record.get("stop_requested") else "paused"
                            record["pause_at_boundary"] = False
                        else:
                            if day not in record["completed_days"]:
                                record["completed_days"].append(day)
                            record.setdefault("day_results", {})[str(day)] = {
                                "success": True,
                                "test_pass_rate": summary.get("average_test_pass_rate"),
                                "message": summary.get("message", ""),
                            }
                            record["current_day"] = int(summary.get("next_day") or day + 1)
                            record["status"] = (
                                "completed" if record["current_day"] > record["days"] else "running"
                            )
                        for commit in summary.get("commits_created", []):
                            if not any(existing.get("hash") == str(commit) for existing in record["commits"]):
                                record["commits"].append(
                                    {"hash": str(commit), "day": day, "timestamp": _timestamp()}
                                )
                    else:
                        record["status"] = "failed"
                        record["error"] = summary.get("error") or summary.get("message") or "Daily execution failed."
                    record["current_task"] = None
                    record["updated_at"] = _timestamp()
                    self._persist()

                status = self.get_status(project_id)
                completed = bool(summary.get("overall_success", True) and not summary.get("paused"))
                self.publish_log(
                    f"Completed Day {day}." if completed else "Daily execution paused or failed.",
                    level="info" if completed else ("warning" if summary.get("paused") else "error"),
                    event="execution.day_completed" if completed else (
                        "execution_stopped" if status["status"] == "stopped"
                        else "execution_paused" if summary.get("paused")
                        else "execution.failed"
                    ),
                    day=day,
                    data={"status": status["status"], "summary": summary},
                )
                if completed:
                    self.publish_log(
                        f"Day {day} completed.",
                        event="day_completed",
                        day=day,
                        data={"status": status["status"]},
                    )
                if self.execution_runner is not None:
                    with self._lock:
                        record = self._projects[project_id]
                        if record.get("pause_requested") and record["status"] == "running":
                            record["status"] = "paused"
                            record["pause_at_boundary"] = True
                        elif record.get("stop_requested") and record["status"] not in {"completed", "failed"}:
                            record["status"] = "stopped"
                            record["pause_at_boundary"] = True
                if not completed:
                    break
                with self._lock:
                    record = self._projects[project_id]
                    if record["status"] == "completed":
                        break
                    if record["pause_requested"]:
                        record["status"] = "paused"
                        record["pause_at_boundary"] = True
                        break
                    if record["stop_requested"]:
                        record["status"] = "stopped"
                        record["pause_at_boundary"] = True
                # A scheduled invocation executes one roadmap day, then waits
                # for the next local schedule instead of consuming the whole plan.
                break

            with self._lock:
                record = self._projects[project_id]
                if record["status"] == "running":
                    record["status"] = "waiting"
                record["elapsed_seconds"] += time.monotonic() - started
                self._run_started.pop(project_id, None)
                record["updated_at"] = _timestamp()
                self._persist()
                finished = record["status"] == "completed"
            if finished:
                self.publish_log(
                    "All planned execution days are complete.",
                    event="execution_finished",
                    day=record["current_day"] - 1,
                )
        except Exception as exc:
            logger.exception("Daily execution failed for project %s.", project_id)
            with self._lock:
                record = self._projects[project_id]
                record["status"] = "failed"
                record["error"] = str(exc)
                record["updated_at"] = _timestamp()
                record["elapsed_seconds"] += time.monotonic() - started
                self._run_started.pop(project_id, None)
                self._persist()
            self.publish_log(
                f"Daily execution failed: {exc}",
                level="error",
                event="execution.failed",
                day=project["current_day"],
            )

    def _completed_day_summary(
        self, project: dict[str, Any], day: int
    ) -> dict[str, Any] | None:
        engine = DayExecutionEngine(self._execution_state_path(project["project_id"], day))
        state = engine.state
        if state is None or state.status != "completed":
            return None
        report_path = (
            self.projects_dir
            / project["project_id"]
            / "memory"
            / "reports"
            / f"day_{day}.md"
        )
        if not report_path.is_file():
            changed_files = {
                file_path
                for commit in state.completed_commits
                for file_path in commit.get("files", [])
            }
            self._write_day_report(
                project,
                day,
                project["plan"],
                engine,
                [],
                [],
                changed_files,
                execution_status="completed",
            )
        return {
            "overall_success": True,
            "next_day": day + 1,
            "message": "Recovered a day whose milestones were already persisted as completed.",
            "error": None,
            "commits_created": [
                str(commit["hash"])
                for commit in state.completed_commits
                if commit.get("hash")
            ],
            "average_test_pass_rate": None,
        }

    def _execute_orchestrator(self, project: dict[str, Any]) -> Any:
        workspace = self.workspaces_dir / project["project_id"]
        workspace.mkdir(parents=True, exist_ok=True)
        if project["repository"] and not any(workspace.iterdir()):
            self._clone_repository(project["repository"], workspace)
        plan_path = self.projects_dir / project["project_id"] / "memory" / "project_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        day = project["current_day"]
        phase = plan["phases"][day - 1]
        execution_dir = self.projects_dir / project["project_id"] / "memory" / "execution"
        engine = DayExecutionEngine(execution_dir / f"day_{day}.json")
        all_commits: list[str] = []
        all_files: set[str] = set()
        test_rates: list[float] = []
        formatter_results: list[str] = []
        def persist_rebased_hash(commit_data: dict[str, Any], rebased_hash: str) -> None:
            previous_hash = commit_data.get("hash")
            if not rebased_hash or previous_hash == rebased_hash:
                return
            commit_data["hash"] = rebased_hash
            engine.update_commit_hash(commit_data["milestone_id"], rebased_hash)
            with self._lock:
                record = self._projects[project["project_id"]]
                for item in record["commits"]:
                    if item.get("hash") == previous_hash:
                        item["hash"] = rebased_hash
                self._persist()

        def execute_milestone(milestone: Milestone) -> dict[str, Any]:
            with self._lock:
                record = self._projects[project["project_id"]]
                record["current_milestone"] = milestone.title
                record["current_task"] = milestone.title
                record["review_status"] = "running"
                record["updated_at"] = _timestamp()
                self._persist()
            self.publish_log(
                f"Executing milestone: {milestone.title}",
                event="milestone_started",
                day=day,
                data={"milestone_id": milestone.milestone_id},
            )
            prior_commit = next(
                (
                    item for item in (engine.state.completed_commits if engine.state else [])
                    if item.get("milestone_id") == milestone.milestone_id
                ),
                None,
            )
            if prior_commit:
                all_files.update(prior_commit.get("files", []))
                all_commits.append(str(prior_commit["hash"]))
                if project["repository"]:
                    self.publish_log("Retrying push for the existing milestone commit.", event="push_started", day=day)
                    push_data = GitHubExecution(GitAgent(project_root=workspace)).push_and_verify(
                        str(prior_commit["hash"])
                    )
                    persist_rebased_hash(prior_commit, str(push_data["commit_hash"]))
                    with self._lock:
                        self._projects[project["project_id"]]["push_status"] = "verified"
                        self._persist()
                    self.publish_log("GitHub push verified.", event="push_completed", day=day, data=push_data)
                return {"success": True, "commit": prior_commit}
            workspace.mkdir(parents=True, exist_ok=True)
            if project["repository"] and not (workspace / ".git").exists():
                self._clone_repository(project["repository"], workspace)
            state_dir = workspace / "memory" / "execution"
            state_dir.mkdir(parents=True, exist_ok=True)
            milestone_plan_path = state_dir / f"day_{day}_{milestone_slug(milestone.milestone_id)}.json"
            task = {
                "day": 1,
                "phase_name": milestone.title,
                "goals": [milestone.description or milestone.title],
                "tasks": [milestone.title],
                "deliverables": phase.get("deliverables", []),
                "testing_focus": phase.get("testing_focus", ""),
                "git_commit_message": f"Day {day} - {milestone.title}",
            }
            one_milestone_plan = dict(plan)
            one_milestone_plan["total_days"] = 1
            one_milestone_plan["phases"] = [task]
            one_milestone_plan["daily_commit_plan"] = [
                {"day": 1, "expected_commits": "1", "milestone": milestone.title}
            ]
            save_project_plan(one_milestone_plan, milestone_plan_path)
            self.publish_log("Review and incremental tests started.", event="review_started", day=day)
            from core.orchestrator import Orchestrator

            orchestrator = Orchestrator(
                project_root=workspace,
                plan_path=milestone_plan_path,
                state_path=state_dir / f"{milestone_slug(milestone.milestone_id)}_state.json",
                tasks_path=state_dir / f"{milestone_slug(milestone.milestone_id)}_tasks.json",
                log_dir=workspace / "logs",
                requirement=project["description"],
                git_agent=_MilestoneGitAgent(project_root=workspace, auto_init=True),
                task_planner=_MilestonePlanner(
                    milestone,
                    state_dir / f"{milestone_slug(milestone.milestone_id)}_tasks.json",
                ),
            )
            orchestrator_logger = logging.getLogger("AutoDev.Orchestrator")
            log_handler = _OrchestratorLogHandler(self, day)
            orchestrator_logger.addHandler(log_handler)
            try:
                result = orchestrator.execute()
            finally:
                orchestrator_logger.removeHandler(log_handler)
            normalized = self._normalize_execution_result(result)
            with self._lock:
                self._projects[project["project_id"]]["review_status"] = (
                    "passed" if normalized.get("overall_success") else "failed"
                )
                self._persist()
            self.publish_log(
                "Milestone review completed." if normalized.get("overall_success") else "Milestone review failed.",
                event="review_completed",
                day=day,
                data={"success": normalized.get("overall_success")},
            )
            if not normalized.get("overall_success"):
                raise RuntimeError(normalized.get("error") or normalized.get("message") or "Milestone validation failed.")
            test_rate = normalized.get("average_test_pass_rate")
            if test_rate is not None:
                test_rates.append(float(test_rate))
            scheduler = CommitScheduler(GitAgent(project_root=workspace))
            changed_files = scheduler.changed_files()
            all_files.update(changed_files)
            formatter = self._format_and_validate(workspace, changed_files)
            formatter_results.append(formatter)
            commit_result = scheduler.create_commit(day, milestone.title)
            commit_data = None
            if commit_result is not None:
                commit_data = {
                    "hash": commit_result.commit_hash,
                    "message": commit_result.commit_message,
                    "day": day,
                    "milestone_id": milestone.milestone_id,
                    "timestamp": commit_result.timestamp,
                    "files": commit_result.files_committed,
                    "formatter": formatter,
                    "static_validation": "passed",
                }
                engine.record_commit(commit_data)
                all_commits.append(str(commit_result.commit_hash))
                all_files.update(commit_result.files_committed)
                with self._lock:
                    record = self._projects[project["project_id"]]
                    record["current_commit_number"] = engine.state.commit_count
                    record["files_changed"] = sorted(all_files)
                    if not any(item.get("hash") == commit_data["hash"] for item in record["commits"]):
                        record["commits"].append(commit_data)
                    self._persist()
                self.publish_log(
                    f"Created commit {str(commit_result.commit_hash)[:8]}.",
                    event="commit_created",
                    day=day,
                    data=commit_data,
                )
                if project["repository"]:
                    with self._lock:
                        self._projects[project["project_id"]]["push_status"] = "running"
                        self._persist()
                    self.publish_log("Pushing commit to GitHub.", event="push_started", day=day)
                    try:
                        push_data = GitHubExecution(GitAgent(project_root=workspace)).push_and_verify(
                            str(commit_result.commit_hash)
                        )
                        persist_rebased_hash(commit_data, str(push_data["commit_hash"]))
                    except Exception as exc:
                        rebased_hash = getattr(exc, "commit_hash", None)
                        if rebased_hash:
                            persist_rebased_hash(commit_data, str(rebased_hash))
                        with self._lock:
                            self._projects[project["project_id"]]["push_status"] = "failed"
                            self._persist()
                        raise
                    with self._lock:
                        self._projects[project["project_id"]]["push_status"] = "verified"
                        self._persist()
                    self.publish_log("GitHub push verified.", event="push_completed", day=day, data=push_data)
            return {"success": True, "commit": commit_data}

        def stop_requested() -> bool:
            with self._lock:
                record = self._projects[project["project_id"]]
                return bool(record.get("pause_requested") or record.get("stop_requested"))

        def publish_milestone_event(event_name: str, milestone: Milestone) -> None:
            if event_name == "milestone_completed":
                self.publish_log(
                    f"Completed milestone: {milestone.title}",
                    event=event_name,
                    day=day,
                    data={"milestone_id": milestone.milestone_id},
                )

        try:
            execution = engine.run_day(
                day,
                phase,
                execute_milestone,
                commit_target=project["daily_commit_target"],
                should_stop=stop_requested,
                on_milestone=publish_milestone_event,
            )
        except Exception:
            self._write_day_report(
                project, day, plan, engine, test_rates, formatter_results, all_files,
                execution_status="failed",
            )
            raise
        report_path = self._write_day_report(
            project,
            day,
            plan,
            engine,
            test_rates,
            formatter_results,
            all_files,
            execution_status=execution["status"],
        )
        with self._lock:
            record = self._projects[project["project_id"]]
            record["current_milestone"] = execution.get("current_milestone")
            record["current_commit_number"] = execution.get("commit_count", 0)
            record["files_changed"] = sorted(all_files)
            record["review_status"] = "passed" if execution.get("success") else execution.get("status", "pending")
            record["execution_report"] = str(report_path)
            self._persist()
        return {
            "overall_success": execution["success"] or execution["status"] == "paused",
            "paused": execution["status"] == "paused",
            "next_day": day if execution["status"] == "paused" else day + 1,
            "message": f"Day {day} milestone execution {execution['status']}.",
            "error": None,
            "commits_created": all_commits,
            "average_test_pass_rate": sum(test_rates) / len(test_rates) if test_rates else None,
        }

    def _write_day_report(
        self,
        project: dict[str, Any],
        day: int,
        plan: dict[str, Any],
        engine: DayExecutionEngine,
        test_rates: list[float],
        formatter_results: list[str],
        files_changed: set[str],
        *,
        execution_status: str,
    ) -> Path:
        report_path = self.projects_dir / project["project_id"] / "memory" / "reports" / f"day_{day}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        state = engine.state
        average_rate = sum(test_rates) / len(test_rates) if test_rates else None
        if average_rate is not None and average_rate <= 1:
            average_rate *= 100
        report_path.write_text(
            "\n".join(
                [
                    f"# Day {day} Execution Report",
                    "",
                    "## Completed Tasks",
                    *[f"- {item.title}" for item in state.milestones if item.status == "completed"],
                    "",
                    "## Commits",
                    *[f"- {commit.get('hash')} - {commit.get('message')}" for commit in state.completed_commits],
                    "",
                    "## Tests Passed",
                    f"- Average pass rate: {average_rate:.1f}%" if average_rate is not None else "- No test metrics reported.",
                    "",
                    "## Static Validation and Formatting",
                    f"- Static validation: {'failed' if execution_status == 'failed' else 'passed'}.",
                    f"- Formatter: {', '.join(formatter_results) if formatter_results else 'not available'}.",
                    "",
                    "## Files Changed",
                    *[f"- {path}" for path in sorted(files_changed)],
                    "",
                    "## Duration",
                    f"- {state.duration_seconds:.2f} seconds",
                    "",
                    "## Problems Fixed",
                    *[
                        f"- Recovered {item['milestone_id']}: {item['error']}"
                        for item in state.failed_tasks if item.get("resolved")
                    ],
                    *(
                        []
                        if any(item.get("resolved") for item in state.failed_tasks)
                        else ["- None recorded."]
                    ),
                    "",
                    "## Unresolved Problems",
                    *[
                        f"- {item['milestone_id']}: {item['error']}"
                        for item in state.failed_tasks if not item.get("resolved")
                    ],
                    *(
                        []
                        if any(not item.get("resolved") for item in state.failed_tasks)
                        else ["- None."]
                    ),
                    "",
                    "## Next Day Preview",
                    f"- {plan['phases'][day]['phase_name']}" if day < len(plan["phases"]) else "- Project complete.",
                ]
            ),
            encoding="utf-8",
        )
        with self._lock:
            record = self._projects[project["project_id"]]
            record["execution_report"] = str(report_path)
            self._persist()
        return report_path

    @staticmethod
    def _format_and_validate(workspace: Path, changed_files: list[str]) -> str:
        python_files = [path for path in changed_files if path.endswith(".py")]
        formatter = shutil.which("black")
        if formatter and python_files:
            result = subprocess.run(
                [formatter, "--quiet", *python_files],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f"Black formatting failed: {result.stderr.strip() or result.stdout.strip()}")
        for relative_path in python_files:
            path = workspace / relative_path
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
            except (OSError, SyntaxError, UnicodeError) as exc:
                raise RuntimeError(f"Static validation failed for {relative_path}: {exc}") from exc
        return "black" if formatter and python_files else "not available"

    def _execution_state_path(self, project_id: str, day: int) -> Path:
        return self.projects_dir / project_id / "memory" / "execution" / f"day_{day}.json"

    @staticmethod
    def _clone_repository(repository: str, workspace: Path) -> None:
        if repository.startswith("git@github.com:"):
            clone_url = repository
        else:
            parsed = urlparse(repository)
            if parsed.scheme != "https" or parsed.hostname != "github.com":
                raise ValueError("Only GitHub HTTPS or SSH repositories can be cloned.")
            clone_url = repository
        result = subprocess.run(
            ["git", "clone", "--", clone_url, str(workspace)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode:
            message = result.stderr.strip() or "git clone failed."
            raise RuntimeError(f"Could not clone the configured repository: {message}")

    def _summary(self, project: dict[str, Any]) -> dict[str, Any]:
        status = self.get_status(project["project_id"])
        return {
            **status,
            "description": project["description"],
            "tech_stack": project["tech_stack"],
            "days": project["days"],
            "working_hours": project["working_hours"],
            "daily_commit_target": project["daily_commit_target"],
            "mode": project["mode"],
            "commits": project["commits"],
        }

    @staticmethod
    def _normalize_execution_result(result: Any) -> dict[str, Any]:
        if hasattr(result, "__dict__"):
            test_result = getattr(result, "test_result", None)
            return {
                "overall_success": bool(getattr(result, "overall_success", True)),
                "next_day": getattr(result, "next_day", None),
                "message": getattr(result, "message", ""),
                "error": getattr(result, "error", None),
                "commits_created": list(getattr(result, "commits_created", [])),
                "average_test_pass_rate": getattr(result, "average_test_pass_rate", None),
                "tests_passed": getattr(test_result, "passed", None),
                "tests_total": getattr(test_result, "total_tests", None),
            }
        if isinstance(result, dict):
            return {
                "overall_success": bool(result.get("overall_success", result.get("success", True))),
                "next_day": result.get("next_day"),
                "message": str(result.get("message", "")),
                "error": result.get("error"),
                "commits_created": list(result.get("commits_created", [])),
                "average_test_pass_rate": result.get("average_test_pass_rate"),
                "tests_passed": result.get("tests_passed"),
                "tests_total": result.get("tests_total"),
            }
        return {
            "overall_success": bool(result),
            "next_day": None,
            "commits_created": [],
            "average_test_pass_rate": None,
        }

    @staticmethod
    def _day_tests(result: dict[str, Any] | None) -> list[str]:
        if not result:
            return []
        if result.get("test_pass_rate") is not None:
            rate = float(result["test_pass_rate"])
            percent = rate * 100 if rate <= 1 else rate
            return [f"Validation pass rate: {percent:.1f}%"]
        return ["Daily execution completed." if result.get("success") else "Daily execution failed."]

    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning("Could not load web UI state from %s: %s", self.state_path, exc)
            return
        if not isinstance(data, dict):
            logger.warning("Ignoring invalid web UI state in %s.", self.state_path)
            return
        with self._lock:
            projects = data.get("projects", {})
            self._projects = projects if isinstance(projects, dict) else {}
            self._active_project_id = data.get("active_project_id")
            logs = data.get("logs", [])
            self._logs = logs if isinstance(logs, list) else []
            self._next_event_id = max(
                (int(item.get("event_id", 0)) for item in self._logs if isinstance(item, dict)),
                default=0,
            ) + 1
            for project_id, record in self._projects.items():
                record.setdefault("schedule_enabled", False)
                record.setdefault("schedule_time", "09:00")
                record.setdefault("timezone", "UTC")
                record.setdefault("last_run_at", None)
                record.setdefault("last_run_local_date", None)
                if record.get("status") == "running":
                    self._interrupted_project_ids.append(project_id)
                    record["status"] = "waiting"

    def _persist(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_project_id": getattr(self, "_active_project_id", None),
            "projects": self._projects,
            "logs": self._logs,
        }
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)


def _command_available(command: str) -> bool:
    from shutil import which

    return which(command) is not None
