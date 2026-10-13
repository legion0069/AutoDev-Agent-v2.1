"""Deterministically ranks available developer tools for a task."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from core.tool_registry import ToolRegistry, is_version_compatible


class ToolSelector:
    """Ranks compatible available tools using task fit, confidence, and history."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def rank(
        self,
        task: str | Mapping[str, Any],
        *,
        language: str | None = None,
        repository: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
        history: Sequence[Mapping[str, Any]] = (),
        capability: str | None = None,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        text = task if isinstance(task, str) else " ".join(
            str(task.get(key, "")) for key in ("title", "description", "goal", "task_type")
        )
        text = text.casefold()
        language = (language or _language_from_context(repository, environment) or _infer_language(text)).casefold()
        required = capability or _infer_capability(text)
        os_name = str((environment or {}).get("operating_system", "")).casefold() or None
        outcomes = _success_by_tool(history)
        ranked = []
        for tool in self.registry.list_tools(available_only=True):
            os_match = (
                os_name is None
                or "any" in {item.casefold() for item in tool.operating_systems}
                or os_name in {item.casefold() for item in tool.operating_systems}
            )
            version_match = version is None or is_version_compatible(tool, version)
            tool_languages = {item.casefold() for item in tool.languages}
            language_match = not language or not tool_languages or language in tool_languages
            cap_match = required in {item.casefold() for item in tool.capabilities} if required else True
            history_success = outcomes.get(tool.name.casefold(), tool.success_rate)
            signals = {
                "task_fit": 1.0 if cap_match else 0.0,
                "language_fit": 1.0 if language_match else 0.0,
                "platform_fit": 1.0 if os_match else 0.0,
                "version_fit": 1.0 if version_match else 0.0,
                "confidence": tool.confidence,
                "historical_success": history_success,
            }
            score = (
                0.35 * signals["task_fit"]
                + 0.20 * signals["language_fit"]
                + 0.10 * signals["platform_fit"]
                + 0.10 * signals["version_fit"]
                + 0.125 * signals["confidence"]
                + 0.125 * signals["historical_success"]
            )
            if os_match and version_match:
                ranked.append({
                    "tool": tool.to_dict(),
                    "score": round(score, 6),
                    "confidence": round(tool.confidence * (1.0 if language_match else 0.75), 6),
                    "signals": signals,
                    "required_capability": required,
                    "language": language or None,
                })
        return sorted(ranked, key=lambda item: (-item["score"], item["tool"]["name"].casefold()))

    def select(self, task: str | Mapping[str, Any], **kwargs: Any) -> dict[str, Any] | None:
        ranked = self.rank(task, **kwargs)
        return ranked[0] if ranked else None

    def recommend(self, task: str | Mapping[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        return self.rank(task, **kwargs)


def _infer_language(value: str) -> str:
    for language, pattern in (
        ("python", r"\bpython\b|\.py\b|pytest"),
        ("typescript", r"\btypescript\b|\.tsx?\b"),
        ("javascript", r"\bjavascript\b|\.jsx?\b|npm"),
        ("java", r"\bjava\b|maven|gradle"),
        ("rust", r"\brust\b|cargo"),
        ("go", r"\bgolang\b|\bgo\b"),
    ):
        if re.search(pattern, value):
            return language
    return ""


def _infer_capability(value: str) -> str:
    for capability, pattern in (
        ("test", r"\btest(?:s|ing)?\b|pytest|jest"),
        ("build", r"\bbuild(?:ing)?\b|compile|package"),
        ("package", r"\binstall(?:ing)?\b|dependency|package manager"),
        ("version_control", r"\bgit\b|commit|branch|history"),
        ("container", r"\bdocker\b|container"),
        ("run", r"\brun\b|execute|launch"),
        ("repository", r"\brepository\b|repo|codebase"),
    ):
        if re.search(pattern, value):
            return capability
    return ""


def _language_from_context(
    repository: Mapping[str, Any] | None,
    environment: Mapping[str, Any] | None,
) -> str:
    for source in (environment or {}, repository or {}):
        value = source.get("primary_language") or source.get("language")
        if value:
            return str(value)
    return ""


def _success_by_tool(history: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    values: dict[str, list[bool]] = {}
    for event in history:
        name = str(event.get("tool", event.get("tool_name", ""))).casefold()
        result = event.get("success")
        if name and isinstance(result, bool):
            values.setdefault(name, []).append(result)
    return {
        name: sum(results) / len(results)
        for name, results in sorted(values.items())
    }
