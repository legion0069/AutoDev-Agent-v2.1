"""Stable dependency-aware backlog ordering for organization-mode projects."""

from __future__ import annotations

from typing import Any, Iterable


class AdaptivePlanner:
    """Orders work by priority while enforcing explicit dependencies deterministically."""

    def order_backlog(
        self,
        tasks: Iterable[Any],
        completed: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        records = [self._as_dict(task) for task in tasks]
        by_id = {str(item["id"]): item for item in records}
        if len(by_id) != len(records):
            raise ValueError("Task IDs must be unique.")
        completed_ids = set(completed)
        missing_dependencies = sorted({
            dependency
            for item in by_id.values()
            for dependency in item.get("dependencies", [])
            if dependency not in by_id and dependency not in completed_ids
        })
        if missing_dependencies:
            raise ValueError(f"Tasks have unresolved dependencies: {missing_dependencies}")
        remaining = {
            task_id: {
                dependency
                for dependency in item.get("dependencies", [])
                if dependency in by_id and dependency not in completed_ids
            }
            for task_id, item in by_id.items()
        }
        ordered: list[dict[str, Any]] = []
        ready = sorted(
            (task_id for task_id, dependencies in remaining.items() if not dependencies),
            key=lambda task_id: self._priority_key(by_id[task_id]),
        )
        while ready:
            task_id = ready.pop(0)
            ordered.append(by_id[task_id])
            for dependent in sorted(remaining):
                if task_id in remaining[dependent]:
                    remaining[dependent].remove(task_id)
                    if not remaining[dependent] and by_id[dependent] not in ordered and dependent not in ready:
                        ready.append(dependent)
            ready.sort(key=lambda key: self._priority_key(by_id[key]))
        if len(ordered) != len(records):
            unresolved = sorted(set(by_id) - {item["id"] for item in ordered})
            raise ValueError(f"Task dependencies contain a cycle: {unresolved}")
        return ordered

    def replan(self, tasks: Iterable[Any], completed: Iterable[str] = ()) -> list[dict[str, Any]]:
        return self.order_backlog(tasks, completed)

    @staticmethod
    def _as_dict(task: Any) -> dict[str, Any]:
        if isinstance(task, dict):
            item = dict(task)
        elif callable(getattr(task, "to_dict", None)):
            item = task.to_dict()
        else:
            raise TypeError("Tasks must be dictionaries or expose to_dict().")
        if not item.get("id"):
            raise ValueError("Every task must have a non-empty id.")
        item["id"] = str(item["id"])
        item["dependencies"] = sorted(set(item.get("dependencies", [])))
        return item

    @staticmethod
    def _priority_key(task: dict[str, Any]) -> tuple[int, str]:
        return int(task.get("priority", 1)), str(task["id"])
