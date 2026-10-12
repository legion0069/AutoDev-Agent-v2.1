"""Deterministic planning validation, repair, and safe parallel opportunity analysis."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class PlanReview:
    valid: bool = True
    issues: list[dict[str, Any]] = field(default_factory=list)
    dependency_violations: list[dict[str, str]] = field(default_factory=list)
    resource_conflicts: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": copy.deepcopy(self.issues),
            "dependency_violations": copy.deepcopy(self.dependency_violations),
            "resource_conflicts": copy.deepcopy(self.resource_conflicts),
        }


@dataclass
class PlanningRevision:
    tasks: Any
    review: PlanReview
    parallel_groups: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [PlanningRevisionEngine._task_dict(task) for task in self.tasks],
            "review": self.review.to_dict(),
            "parallel_groups": copy.deepcopy(self.parallel_groups),
        }


class PlanningRevisionEngine:
    """Checks task plans and repairs only deterministic, mechanically safe defects."""

    def review(self, plan: Any) -> PlanReview:
        tasks = self._tasks(plan)
        review = PlanReview()
        by_id: dict[str, Any] = {}
        for index, task in enumerate(tasks):
            task_id = str(self._get(task, "id", self._get(task, "task_id", "")))
            if not task_id:
                review.issues.append({"type": "missing_id", "index": index})
            elif task_id in by_id:
                review.issues.append({"type": "duplicate_id", "task_id": task_id})
            else:
                by_id[task_id] = task

        completed = {
            task_id for task_id, task in by_id.items()
            if str(self._get(task, "status", "")).lower() in {"done", "completed", "success"}
        }
        for task_id, task in sorted(by_id.items()):
            dependencies = self._dependencies(task)
            for dependency in dependencies:
                if dependency not in by_id:
                    review.dependency_violations.append(
                        {"task_id": task_id, "dependency": dependency, "reason": "missing dependency"}
                    )
                elif dependency == task_id:
                    review.dependency_violations.append(
                        {"task_id": task_id, "dependency": dependency, "reason": "self dependency"}
                    )
                elif str(self._get(task, "status", "")).lower() in {"done", "completed", "success"} and dependency not in completed:
                    review.dependency_violations.append(
                        {"task_id": task_id, "dependency": dependency, "reason": "completed before prerequisite"}
                    )
        for left_index, left in enumerate(tasks):
            for right in tasks[left_index + 1:]:
                left_id = str(self._get(left, "id", self._get(left, "task_id", "")))
                right_id = str(self._get(right, "id", self._get(right, "task_id", "")))
                overlap = sorted(set(self._resources(left)) & set(self._resources(right)))
                if overlap and not self._has_dependency_path(left_id, right_id, by_id) and not self._has_dependency_path(right_id, left_id, by_id):
                    review.resource_conflicts.append({
                        "task_a": left_id, "task_b": right_id, "resources": overlap,
                    })
        review.issues.extend(self._cycle_issues(by_id))
        review.valid = not (
            review.issues or review.dependency_violations or review.resource_conflicts
        )
        return review

    def repair(self, plan: Any) -> Any:
        revised, tasks, wrapper_key = self._copy_plan(plan)
        by_id: dict[str, Any] = {}
        for task in tasks:
            task_id = str(self._get(task, "id", self._get(task, "task_id", "")))
            if task_id and task_id not in by_id:
                by_id[task_id] = task
        for task_id in sorted(by_id):
            task = by_id[task_id]
            dependencies = [
                dep for dep in self._dependencies(task)
                if dep in by_id and dep != task_id
            ]
            self._set_dependencies(task, list(dict.fromkeys(dependencies)))
        while True:
            cycle = self._find_cycle(by_id)
            if not cycle:
                break
            source, dependency = sorted(zip(cycle, cycle[1:]))[-1]
            task = by_id[source]
            self._set_dependencies(
                task, [item for item in self._dependencies(task) if item != dependency]
            )
        if isinstance(revised, dict) and wrapper_key is not None:
            revised[wrapper_key] = tasks
            return revised
        return tasks

    def optimize(self, plan: Any) -> PlanningRevision:
        repaired = self.repair(plan)
        tasks = self._tasks(repaired)
        review = self.review(repaired)
        by_id = {
            str(self._get(task, "id", self._get(task, "task_id", ""))): task
            for task in tasks
        }
        remaining = set(by_id)
        completed: set[str] = set()
        groups: list[list[str]] = []
        while remaining:
            ready = sorted(
                task_id for task_id in remaining
                if set(self._dependencies(by_id[task_id])) <= completed
            )
            if not ready:
                break
            group: list[str] = []
            resources: set[str] = set()
            for task_id in ready:
                task_resources = set(self._resources(by_id[task_id]))
                if not task_resources.intersection(resources):
                    group.append(task_id)
                    resources.update(task_resources)
            if not group:
                group = [ready[0]]
            groups.append(group)
            completed.update(group)
            remaining.difference_update(group)
        return PlanningRevision(repaired, review, groups)

    @classmethod
    def _tasks(cls, plan: Any) -> list[Any]:
        if isinstance(plan, Mapping):
            tasks = plan.get("tasks", [])
        else:
            tasks = plan
        return list(tasks) if isinstance(tasks, Sequence) and not isinstance(tasks, (str, bytes)) else []

    @classmethod
    def _copy_plan(cls, plan: Any) -> tuple[Any, list[Any], str | None]:
        revised = copy.deepcopy(plan)
        if isinstance(revised, dict):
            key = "tasks" if isinstance(revised.get("tasks"), list) else None
            return revised, revised.get(key, []) if key else [], key
        return revised, cls._tasks(revised), None

    @staticmethod
    def _task_dict(task: Any) -> dict[str, Any]:
        if isinstance(task, Mapping):
            return dict(task)
        if hasattr(task, "to_dict"):
            return task.to_dict()
        if hasattr(task, "__dict__"):
            return dict(task.__dict__)
        return {"value": str(task)}

    @staticmethod
    def _get(task: Any, key: str, default: Any = None) -> Any:
        return task.get(key, default) if isinstance(task, Mapping) else getattr(task, key, default)

    @classmethod
    def _dependencies(cls, task: Any) -> list[str]:
        values = cls._get(task, "dependencies", []) or []
        return [str(value) for value in values if value]

    @staticmethod
    def _set_dependencies(task: Any, dependencies: list[str]) -> None:
        if isinstance(task, dict):
            task["dependencies"] = dependencies
        else:
            task.dependencies = dependencies

    @classmethod
    def _resources(cls, task: Any) -> list[str]:
        values = cls._get(task, "resources", cls._get(task, "estimated_files", [])) or []
        return [str(value) for value in ([values] if isinstance(values, str) else values) if value]

    @classmethod
    def _has_dependency_path(cls, source: str, target: str, by_id: Mapping[str, Any]) -> bool:
        pending = list(cls._dependencies(by_id.get(target, {})))
        seen: set[str] = set()
        while pending:
            item = pending.pop()
            if item == source:
                return True
            if item not in seen:
                seen.add(item)
                pending.extend(cls._dependencies(by_id.get(item, {})))
        return False

    @classmethod
    def _find_cycle(cls, by_id: Mapping[str, Any]) -> list[str]:
        visited: set[str] = set()
        active: list[str] = []
        def visit(task_id: str) -> list[str]:
            if task_id in active:
                return active[active.index(task_id):] + [task_id]
            if task_id in visited:
                return []
            active.append(task_id)
            for dependency in sorted(cls._dependencies(by_id[task_id])):
                if dependency in by_id:
                    result = visit(dependency)
                    if result:
                        return result
            active.pop()
            visited.add(task_id)
            return []
        for task_id in sorted(by_id):
            result = visit(task_id)
            if result:
                return result
        return []

    @classmethod
    def _cycle_issues(cls, by_id: Mapping[str, Any]) -> list[dict[str, Any]]:
        cycle = cls._find_cycle(by_id)
        return [{"type": "dependency_cycle", "tasks": cycle}] if cycle else []
