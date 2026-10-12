"""Dependency- and resource-aware public scheduler for multi-agent tasks."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from core.execution_scheduler import ExecutionScheduler, ScheduledTask
from core.planning_revision import PlanningRevisionEngine


class ParallelTaskScheduler(ExecutionScheduler):
    """Extends the existing worker pool with file/resource serialization."""

    @staticmethod
    def safe_parallel_groups(tasks: Any) -> list[list[str]]:
        revision = PlanningRevisionEngine().optimize(tasks)
        return revision.parallel_groups

    def schedule(
        self,
        tasks: Iterable[ScheduledTask],
    ) -> dict[str, Any]:
        """Executes dependency-valid tasks and returns results in task-ID order."""
        return self.execute(tasks)


ParallelScheduler = ParallelTaskScheduler
