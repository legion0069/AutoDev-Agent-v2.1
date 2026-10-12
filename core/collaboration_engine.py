"""Opt-in task collaboration using safe planning and deterministic scheduling."""

from __future__ import annotations

import threading
from typing import Any, Callable, Mapping, Optional

from core.execution_scheduler import ExecutionScheduler, ScheduledTask
from core.multi_agent_runtime import MultiAgentRuntime
from core.planning_revision import PlanningRevisionEngine


class CollaborationEngine:
    """Coordinates dependencies, agent assignment, progress, and completion events."""

    def __init__(
        self,
        runtime: Optional[MultiAgentRuntime] = None,
        scheduler: Optional[ExecutionScheduler] = None,
        planning_engine: Optional[PlanningRevisionEngine] = None,
    ) -> None:
        self.runtime = runtime
        self.scheduler = scheduler or ExecutionScheduler()
        self.planning_engine = planning_engine or PlanningRevisionEngine()
        self._lock = threading.RLock()
        self._progress: dict[str, dict[str, Any]] = {}
        self._barriers: dict[str, threading.Barrier] = {}

    def plan(self, tasks: Any) -> dict[str, Any]:
        revision = self.planning_engine.optimize(tasks)
        task_list = revision.tasks.get("tasks", []) if isinstance(revision.tasks, dict) else revision.tasks
        with self._lock:
            for task in task_list:
                task_id = self._get(task, "id", self._get(task, "task_id", ""))
                if task_id:
                    self._progress.setdefault(str(task_id), {"status": "planned", "result": None})
        return revision.to_dict()

    def execute(
        self,
        tasks: Any,
        handlers: Optional[Mapping[str, Callable[[Any], Any]]] = None,
        max_workers: Optional[int] = None,
    ) -> dict[str, Any]:
        task_list = tasks.get("tasks", []) if isinstance(tasks, dict) else tasks
        task_list = list(task_list or [])
        if max_workers is not None:
            scheduler = ExecutionScheduler(max_workers=max_workers)
        else:
            scheduler = self.scheduler
        handlers = handlers or {}
        ids = {
            str(self._get(task, "id", self._get(task, "task_id", ""))): task
            for task in task_list
        }
        scheduled = []
        for task_id in sorted(ids):
            task = ids[task_id]
            fn = handlers.get(task_id) or self._get(task, "function")
            if not callable(fn):
                raise ValueError(f"No callable handler provided for task {task_id!r}")
            dependency_values = self._get(task, "dependencies", []) or []
            if isinstance(dependency_values, str):
                dependency_values = [dependency_values]
            resource_values = self._get(
                task,
                "resources",
                self._get(task, "estimated_files", []),
            ) or []
            if isinstance(resource_values, str):
                resource_values = [resource_values]
            dependencies = set(str(item) for item in dependency_values)
            resources = set(str(item) for item in resource_values)
            def runner(task_obj: Any = task, handler: Callable[[Any], Any] = fn, key: str = task_id) -> Any:
                with self._lock:
                    self._progress[key] = {"status": "running", "result": None}
                result = handler(task_obj)
                with self._lock:
                    self._progress[key] = {"status": "completed", "result": result}
                if self.runtime is not None:
                    self.runtime.broadcast(
                        "collaboration_engine",
                        {"event": "TASK_COMPLETED", "task_id": key, "status": "completed"},
                    )
                return result
            scheduled.append(ScheduledTask(
                task_id=task_id,
                function=runner,
                dependencies=dependencies,
                resources=resources,
            ))
        return scheduler.execute(scheduled)

    def progress(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {key: dict(self._progress[key]) for key in sorted(self._progress)}

    def notify_completion(self, task_id: str, result: Any = None, success: bool = True) -> None:
        with self._lock:
            self._progress[task_id] = {
                "status": "completed" if success else "failed",
                "result": result,
            }
        if self.runtime is not None:
            self.runtime.broadcast(
                "collaboration_engine",
                {
                    "event": "TASK_COMPLETED" if success else "TASK_FAILED",
                    "task_id": task_id,
                    "status": "completed" if success else "failed",
                },
            )

    def synchronize(self, barrier_id: str, parties: int, timeout: Optional[float] = None) -> bool:
        if parties < 1:
            raise ValueError("parties must be at least one")
        with self._lock:
            barrier = self._barriers.setdefault(barrier_id, threading.Barrier(parties))
        try:
            barrier.wait(timeout=timeout)
            return True
        except threading.BrokenBarrierError:
            return False

    @staticmethod
    def _get(value: Any, name: str, default: Any = None) -> Any:
        return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)
