"""Durable day and milestone execution state for the V5.2 web workflow."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Milestone:
    milestone_id: str
    title: str
    description: str = ""
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


@dataclass
class DayExecutionState:
    current_day: int
    current_milestone: str | None = None
    milestones: list[Milestone] = field(default_factory=list)
    completed_milestones: list[str] = field(default_factory=list)
    commit_count: int = 0
    completed_commits: list[dict[str, Any]] = field(default_factory=list)
    failed_tasks: list[dict[str, Any]] = field(default_factory=list)
    retry_queue: list[str] = field(default_factory=list)
    started_at: float | None = None
    duration_seconds: float = 0.0
    status: str = "pending"


class DayExecutionEngine:
    """Splits a roadmap day into resumable milestones and persists each transition."""

    def __init__(self, state_path: str | Path) -> None:
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state: DayExecutionState | None = self.load()

    def load(self) -> DayExecutionState | None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"Invalid execution state in {self.state_path}.")
        milestones = [
            Milestone(**item)
            for item in data.get("milestones", [])
            if isinstance(item, dict)
        ]
        return DayExecutionState(
            current_day=int(data["current_day"]),
            current_milestone=data.get("current_milestone"),
            milestones=milestones,
            completed_milestones=list(data.get("completed_milestones", [])),
            commit_count=int(data.get("commit_count", 0)),
            completed_commits=list(data.get("completed_commits", [])),
            failed_tasks=list(data.get("failed_tasks", [])),
            retry_queue=list(data.get("retry_queue", [])),
            started_at=data.get("started_at"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            status=str(data.get("status", "pending")),
        )

    @staticmethod
    def milestones_for_day(day: int, phase: dict[str, Any]) -> list[Milestone]:
        tasks = phase.get("tasks") or [phase.get("phase_name", f"Day {day} work")]
        milestones = []
        for index, task in enumerate(tasks, 1):
            if isinstance(task, dict):
                title = str(
                    task.get("title") or task.get("name") or f"Milestone {index}"
                )
                description = str(task.get("description") or "")
                milestone_id = str(task.get("id") or f"day-{day}-milestone-{index}")
            else:
                title = str(task)
                description = ""
                milestone_id = f"day-{day}-milestone-{index}"
            milestones.append(Milestone(milestone_id, title, description))
        return milestones

    def prepare_day(self, day: int, phase: dict[str, Any]) -> DayExecutionState:
        if (
            self.state
            and self.state.current_day == day
            and self.state.status != "completed"
        ):
            existing = {item.milestone_id for item in self.state.milestones}
            planned = self.milestones_for_day(day, phase)
            if existing == {item.milestone_id for item in planned}:
                return self.state
        self.state = DayExecutionState(
            current_day=day,
            milestones=self.milestones_for_day(day, phase),
        )
        self._save()
        return self.state

    def run_day(
        self,
        day: int,
        phase: dict[str, Any],
        execute_milestone: Callable[[Milestone], dict[str, Any]],
        *,
        commit_target: int,
        should_stop: Callable[[], bool] | None = None,
        on_milestone: Callable[[str, Milestone], None] | None = None,
    ) -> dict[str, Any]:
        state = self.prepare_day(day, phase)
        if state.status == "running" and state.started_at is not None:
            state.duration_seconds += max(0.0, time.time() - state.started_at)
        state.status = "running"
        run_started = time.time()
        state.started_at = run_started
        self._save()
        for milestone in state.milestones:
            if milestone.status == "completed":
                continue
            if should_stop and should_stop():
                state.status = "paused"
                self._save()
                break
            state.current_milestone = milestone.milestone_id
            milestone.status = "running"
            milestone.started_at = milestone.started_at or _now()
            self._save()
            if on_milestone:
                on_milestone("milestone_started", milestone)
            try:
                result = execute_milestone(milestone)
                if not result.get("success", False):
                    raise RuntimeError(
                        str(
                            result.get("error")
                            or result.get("message")
                            or "Milestone failed."
                        )
                    )
                milestone.status = "completed"
                milestone.completed_at = _now()
                milestone.error = None
                state.completed_milestones.append(milestone.milestone_id)
                state.retry_queue = [
                    item for item in state.retry_queue if item != milestone.milestone_id
                ]
                for failure in state.failed_tasks:
                    if failure.get("milestone_id") == milestone.milestone_id:
                        failure["resolved"] = True
                commit = result.get("commit")
                if commit:
                    self.record_commit(commit)
                if on_milestone:
                    on_milestone("milestone_completed", milestone)
            except Exception as exc:
                milestone.status = "failed"
                milestone.error = str(exc)
                state.failed_tasks.append(
                    {
                        "milestone_id": milestone.milestone_id,
                        "error": str(exc),
                        "timestamp": _now(),
                    }
                )
                if milestone.milestone_id not in state.retry_queue:
                    state.retry_queue.append(milestone.milestone_id)
                state.status = "failed"
                state.duration_seconds += max(0.0, time.time() - run_started)
                self._save()
                raise
            finally:
                self._save()

        state.duration_seconds += max(0.0, time.time() - run_started)
        if all(item.status == "completed" for item in state.milestones):
            state.status = "completed"
            state.current_milestone = None
        self._save()
        return {
            "success": state.status == "completed",
            "status": state.status,
            "current_day": state.current_day,
            "current_milestone": state.current_milestone,
            "completed_milestones": list(state.completed_milestones),
            "remaining_milestones": [
                item.milestone_id
                for item in state.milestones
                if item.status != "completed"
            ],
            "commit_count": state.commit_count,
            "commit_target": commit_target,
            "commits": list(state.completed_commits),
            "failed_tasks": list(state.failed_tasks),
            "retry_queue": list(state.retry_queue),
            "duration_seconds": state.duration_seconds,
        }

    def record_commit(self, commit: dict[str, Any]) -> None:
        if self.state is None:
            raise RuntimeError("No execution state is available.")
        commit_hash = commit.get("hash")
        if commit_hash and not any(
            item.get("hash") == commit_hash for item in self.state.completed_commits
        ):
            self.state.completed_commits.append(commit)
            self.state.commit_count += 1
            self._save()

    def update_commit_hash(self, milestone_id: str, commit_hash: str) -> None:
        if self.state is None:
            raise RuntimeError("No execution state is available.")
        for commit in self.state.completed_commits:
            if commit.get("milestone_id") == milestone_id:
                commit["hash"] = commit_hash
        self._save()

    def retry_failed(self, milestone_id: str) -> None:
        if self.state is None:
            raise RuntimeError("No execution state is available.")
        milestone = next(
            (
                item
                for item in self.state.milestones
                if item.milestone_id == milestone_id
            ),
            None,
        )
        if milestone is None:
            raise KeyError(f"Unknown milestone: {milestone_id}")
        milestone.status = "pending"
        milestone.error = None
        self.state.status = "pending"
        if milestone_id not in self.state.retry_queue:
            self.state.retry_queue.append(milestone_id)
        self._save()

    def _save(self) -> None:
        if self.state is None:
            return
        payload = asdict(self.state)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.state_path)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def milestone_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "milestone"
