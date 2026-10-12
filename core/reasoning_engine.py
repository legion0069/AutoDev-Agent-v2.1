"""Deterministic, explainable structured reasoning for engineering tasks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Optional

from core.reasoning_cache import ReasoningCache


class ReasoningEngine:
    """Produces concise decision-support summaries, never private reasoning traces."""

    def __init__(
        self,
        project_root: str | Path = ".",
        cache_manager: Optional[Any] = None,
        cache_root: Optional[str | Path] = None,
    ) -> None:
        self.cache = ReasoningCache("summaries", project_root, cache_manager, cache_root)

    def reason(
        self,
        goal: str | Mapping[str, Any],
        context: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        goal_text = self._text(goal)
        safe_context = self._json_safe(context or {})
        cache_key = {"goal": goal_text, "context": safe_context}
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        sentences = [
            segment.strip(" \t\r\n.;")
            for segment in re.split(r"[\n;]+|(?<=[.!?])\s+", goal_text)
            if segment.strip(" \t\r\n.;")
        ]
        steps = list(dict.fromkeys(sentences))[:8]
        files = self._files(safe_context)
        terms = set(re.findall(r"[a-z0-9_]+", goal_text.lower()))
        risk_terms = {"security", "migration", "delete", "breaking", "production", "data", "auth"}
        risk_score = min(1.0, 0.2 + 0.12 * len(terms & risk_terms))
        if not goal_text:
            confidence = 0.0
        elif files:
            confidence = min(0.95, 0.70 + min(len(files), 5) * 0.04)
        else:
            confidence = 0.60
        effort_units = max(1, len(steps)) + min(len(files), 10)
        result = {
            "summary": goal_text[:500],
            "steps": steps,
            "constraints": self._constraints(safe_context),
            "dependencies": sorted(str(item) for item in safe_context.get("dependencies", []) if item),
            "estimated_cost": {
                "effort_units": effort_units,
                "estimated_minutes": effort_units * 15,
                "affected_files": len(files),
            },
            "risk": {
                "score": round(risk_score, 4),
                "level": "high" if risk_score >= 0.60 else "medium" if risk_score >= 0.35 else "low",
                "factors": sorted(terms & risk_terms),
            },
            "confidence": round(confidence, 4),
            "expected_benefit": self.expected_benefit(goal_text, safe_context),
            "feasibility": self.feasibility(goal_text, safe_context),
        }
        self.cache.set(cache_key, result)
        return result

    def summarize(self, content: Any, max_length: int = 500) -> str:
        text = self._text(content)
        return text[:max(0, max_length)].strip()

    def estimate_cost(self, task: Any, context: Optional[Mapping[str, Any]] = None) -> dict[str, int]:
        return self.reason(task, context)["estimated_cost"]

    def assess_risk(self, task: Any, context: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        return self.reason(task, context)["risk"]

    def confidence(self, task: Any, context: Optional[Mapping[str, Any]] = None) -> float:
        return float(self.reason(task, context)["confidence"])

    def expected_benefit(
        self, task: Any, context: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        text = self._text(task).lower()
        positive_terms = {"improve", "faster", "fix", "support", "reliable", "automate", "reduce"}
        matched = sorted(set(re.findall(r"[a-z0-9_]+", text)) & positive_terms)
        return {
            "score": round(min(1.0, 0.35 + 0.15 * len(matched)), 4),
            "indicators": matched,
        }

    def feasibility(self, task: Any, context: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        text = self._text(task).lower()
        blocked = sorted(
            term for term in ("unavailable dependency", "unknown prerequisite", "blocked")
            if term in text
        )
        return {
            "feasible": not blocked,
            "confidence": 0.8 if not blocked else 0.3,
            "blockers": blocked,
        }

    def statistics(self) -> dict[str, int | float]:
        return self.cache.statistics()

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, Mapping):
            for key in ("goal", "title", "description", "summary", "task"):
                candidate = value.get(key)
                if candidate:
                    return str(candidate).strip()
            return ""
        return str(value or "").strip()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): ReasoningEngine._json_safe(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                if not any(token in str(key).lower() for token in ("chain_of_thought", "private_reasoning"))
            }
        if isinstance(value, (list, tuple, set)):
            items = [ReasoningEngine._json_safe(item) for item in value]
            return sorted(items, key=str) if isinstance(value, set) else items
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "to_dict"):
            return ReasoningEngine._json_safe(value.to_dict())
        return str(value)

    @staticmethod
    def _files(context: Mapping[str, Any]) -> list[str]:
        values = context.get("files", context.get("estimated_files", []))
        if isinstance(values, str):
            values = [values]
        return sorted({str(Path(item).as_posix()) for item in values if item})

    @staticmethod
    def _constraints(context: Mapping[str, Any]) -> list[str]:
        values = context.get("constraints", [])
        if isinstance(values, str):
            values = [values]
        return sorted({str(item) for item in values if item})
