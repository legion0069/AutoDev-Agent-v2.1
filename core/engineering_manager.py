"""Engineering execution reporting for the opt-in organization workflow."""

from __future__ import annotations

import copy
import threading
from typing import Any, Optional


class EngineeringManager:
    """Tracks task progress and produces deterministic productivity and quality reports."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, dict[str, Any]] = {}

    def record_task(
        self,
        task_id: str,
        status: str,
        team_id: Optional[str] = None,
        quality_score: Optional[float] = None,
        review_duration_seconds: float = 0.0,
    ) -> dict[str, Any]:
        if not task_id or not status:
            raise ValueError("Task ID and status must not be empty.")
        if review_duration_seconds < 0:
            raise ValueError("Review duration must not be negative.")
        with self._lock:
            record = {
                "task_id": task_id,
                "status": status.upper(),
                "team_id": team_id,
                "quality_score": quality_score,
                "review_duration_seconds": float(review_duration_seconds),
            }
            self._tasks[task_id] = record
            return copy.deepcopy(record)

    def generate_report(
        self,
        project_dashboard: Optional[dict[str, Any]] = None,
        team_statuses: Optional[list[dict[str, Any]]] = None,
        deployment_readiness: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        with self._lock:
            tasks = list(self._tasks.values())
            completed = sum(item["status"] in {"COMPLETED", "DONE"} for item in tasks)
            blocked = sum(item["status"] in {"BLOCKED", "FAILED"} for item in tasks)
            scores = [float(item["quality_score"]) for item in tasks if item["quality_score"] is not None]
            review_durations = [item["review_duration_seconds"] for item in tasks]
            return {
                "task_count": len(tasks),
                "completed_tasks": completed,
                "blocked_tasks": blocked,
                "productivity": round(completed / len(tasks), 4) if tasks else 0.0,
                "average_quality": round(sum(scores) / len(scores), 2) if scores else 0.0,
                "review_bottleneck_seconds": round(sum(review_durations), 3),
                "teams": copy.deepcopy(sorted(team_statuses or [], key=lambda item: item.get("team_id", ""))),
                "projects": copy.deepcopy(project_dashboard or {"project_count": 0, "projects": []}),
                "deployment_readiness": copy.deepcopy(deployment_readiness or {}),
            }

    def task_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(self._tasks[key]) for key in sorted(self._tasks)]
