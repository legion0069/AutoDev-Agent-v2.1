"""Deterministic, non-executing plans for environment-aware engineering work."""

from __future__ import annotations

from typing import Any, Mapping

from core.tool_selector import ToolSelector


class ToolExecutionPlanner:
    """Describes an ordered workflow and recommended tools, without running them."""

    STEPS = (
        ("repository_scan", "repository", "Analyze repository structure and architecture."),
        ("dependency_analysis", "package", "Inspect dependency manifests, imports, and risk."),
        ("git_analysis", "version_control", "Inspect local Git history and file hotspots."),
        ("environment_scan", "run", "Inspect available runtimes, tools, and host resources."),
        ("implementation", "run", "Use selected implementation tools; require explicit approval to execute."),
        ("testing", "test", "Validate affected behavior using impacted tests."),
        ("documentation", "run", "Update documentation affected by the change."),
        ("benchmarks", "run", "Measure relevant performance after validation."),
    )

    def __init__(self, selector: ToolSelector) -> None:
        self.selector = selector

    def plan(
        self,
        task: str | Mapping[str, Any],
        *,
        environment: Mapping[str, Any] | None = None,
        repository: Mapping[str, Any] | None = None,
        available_steps: set[str] | None = None,
    ) -> dict[str, Any]:
        selected_steps = [
            item for item in self.STEPS
            if available_steps is None or item[0] in available_steps
        ]
        steps = []
        for order, (step_id, capability, description) in enumerate(selected_steps, 1):
            selected = self.selector.select(
                task if step_id == "implementation" else f"{step_id} {description}",
                environment=environment,
                repository=repository,
                capability=capability,
            )
            steps.append({
                "order": order,
                "id": step_id,
                "description": description,
                "tool": selected["tool"]["name"] if selected else None,
                "confidence": selected["confidence"] if selected else 0.0,
                "requires_execution_approval": step_id in {"implementation", "testing", "documentation", "benchmarks"},
            })
        return {
            "task": task if isinstance(task, str) else str(task.get("title", task.get("description", ""))),
            "deterministic": True,
            "execution_performed": False,
            "steps": steps,
        }
