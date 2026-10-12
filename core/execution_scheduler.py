"""Dependency-aware concurrent execution of independent engineering tasks."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Set


@dataclass
class ScheduledTask:
    """A callable and the task identifiers that must finish before it starts."""

    task_id: str
    function: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    resources: Set[str] = field(default_factory=set)


class ExecutionScheduler:
    """Runs ready tasks concurrently while enforcing a deterministic DAG order."""

    def __init__(
        self,
        max_workers: int = 4,
        resource_limits: Optional[Dict[str, int]] = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1.")
        self.max_workers = max_workers
        self.resource_limits = dict(resource_limits or {})
        if any(not name or limit < 1 for name, limit in self.resource_limits.items()):
            raise ValueError("resource names must be non-empty and capacities at least 1.")
        self._tasks: Dict[str, ScheduledTask] = {}

    def add_task(
        self,
        task_id: str,
        function: Callable[..., Any],
        args: Optional[tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        dependencies: Optional[Set[str]] = None,
        resources: Optional[Set[str]] = None,
    ) -> None:
        """Registers a task; duplicate identifiers are rejected."""
        if not task_id:
            raise ValueError("task_id must not be empty.")
        if task_id in self._tasks:
            raise ValueError(f"Task {task_id!r} is already scheduled.")
        self._tasks[task_id] = ScheduledTask(
            task_id=task_id,
            function=function,
            args=args or (),
            kwargs=kwargs or {},
            dependencies=set(dependencies or ()),
            resources=set(resources or ()),
        )

    def execute(self, tasks: Optional[Iterable[ScheduledTask]] = None) -> Dict[str, Any]:
        """Executes registered or supplied tasks, propagating the first task failure."""
        task_map = dict(self._tasks)
        if tasks is not None:
            for task in tasks:
                if task.task_id in task_map:
                    raise ValueError(f"Task {task.task_id!r} is already scheduled.")
                task_map[task.task_id] = task
        self._validate_graph(task_map)

        results: Dict[str, Any] = {}
        pending = set(task_map)
        running: Dict[Future[Any], str] = {}
        active_resources: Dict[str, int] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while pending or running:
                ready = sorted(
                    task_id
                    for task_id in pending
                    if task_map[task_id].dependencies.issubset(results)
                    and all(
                        active_resources.get(resource, 0)
                        < self.resource_limits.get(resource, 1)
                        for resource in task_map[task_id].resources
                    )
                )
                while ready and len(running) < self.max_workers:
                    task_id = ready.pop(0)
                    task = task_map[task_id]
                    future = executor.submit(task.function, *task.args, **task.kwargs)
                    running[future] = task_id
                    pending.remove(task_id)
                    for resource in task.resources:
                        active_resources[resource] = active_resources.get(resource, 0) + 1

                if not running:
                    raise RuntimeError("Scheduler reached a blocked state after graph validation.")

                completed, _ = wait(running, return_when=FIRST_COMPLETED)
                failures: list[tuple[str, Exception]] = []
                for future in sorted(completed, key=lambda item: running[item]):
                    task_id = running.pop(future)
                    for resource in task_map[task_id].resources:
                        active_resources[resource] -= 1
                        if active_resources[resource] == 0:
                            del active_resources[resource]
                    try:
                        results[task_id] = future.result()
                    except Exception as err:
                        failures.append((task_id, err))
                if failures:
                    task_id, error = sorted(failures, key=lambda item: item[0])[0]
                    raise RuntimeError(f"Scheduled task {task_id!r} failed.") from error

        return {task_id: results[task_id] for task_id in sorted(results)}

    def run(self, tasks: Optional[Iterable[ScheduledTask]] = None) -> Dict[str, Any]:
        """Alias for :meth:`execute`."""
        return self.execute(tasks)

    @staticmethod
    def _validate_graph(tasks: Dict[str, ScheduledTask]) -> None:
        for task_id, task in tasks.items():
            unknown = task.dependencies - tasks.keys()
            if unknown:
                raise ValueError(
                    f"Task {task_id!r} has unknown dependencies: {', '.join(sorted(unknown))}."
                )

        remaining = {task_id: set(task.dependencies) for task_id, task in tasks.items()}
        while remaining:
            ready = sorted(task_id for task_id, deps in remaining.items() if not deps)
            if not ready:
                raise ValueError("Scheduled tasks contain a dependency cycle.")
            for task_id in ready:
                remaining.pop(task_id)
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
