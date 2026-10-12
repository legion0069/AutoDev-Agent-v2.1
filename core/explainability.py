"""Safe, structured explanations for decisions and plans."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


class ExplainabilityEngine:
    """Formats public evidence and outcomes without exposing internal reasoning traces."""

    _PRIVATE_KEYS = {
        "chain_of_thought", "private_reasoning", "internal_reasoning",
        "reasoning_trace", "hidden_reasoning", "scratchpad",
    }

    def explain_decision(self, decision: Any) -> dict[str, Any]:
        data = self._safe_mapping(decision)
        return {
            "type": "decision",
            "summary": self._first(data, "summary", "decision", "recommendation", "winner"),
            "selected_option": data.get("selected_option", data.get("winner", data.get("option"))),
            "confidence": self._bounded(data.get("confidence", data.get("score", 0.0))),
            "evidence": self._string_list(data.get("evidence", data.get("factors", []))),
            "tradeoffs": self._string_list(data.get("tradeoffs", [])),
        }

    def explain_plan(self, plan: Any) -> dict[str, Any]:
        tasks = plan.get("tasks", []) if isinstance(plan, Mapping) else plan
        tasks = list(tasks) if isinstance(tasks, Sequence) and not isinstance(tasks, (str, bytes)) else []
        entries = []
        for task in tasks:
            data = self._safe_mapping(task)
            entries.append({
                "id": data.get("id", data.get("task_id", "")),
                "summary": self._first(data, "title", "summary", "description"),
                "dependencies": sorted(str(item) for item in data.get("dependencies", []) if item),
            })
        entries.sort(key=lambda item: str(item["id"]))
        return {"type": "plan", "task_count": len(entries), "tasks": entries}

    def explain_task(self, task: Any, outcome: Any = None) -> dict[str, Any]:
        data = self._safe_mapping(task)
        outcome_data = self._safe_mapping(outcome)
        return {
            "type": "task",
            "task_id": data.get("id", data.get("task_id", "")),
            "summary": self._first(data, "title", "summary", "description"),
            "status": outcome_data.get("status", data.get("status", "")),
            "result": self._first(outcome_data, "summary", "message", "result"),
            "evidence": self._string_list(outcome_data.get("evidence", [])),
        }

    def format_report(self, report: Any) -> dict[str, Any]:
        data = self._safe_mapping(report)
        return {
            "summary": self._first(data, "summary", "title", "message"),
            "findings": self._string_list(data.get("findings", [])),
            "recommendations": self._string_list(data.get("recommendations", [])),
            "confidence": self._bounded(data.get("confidence", 0.0)),
        }

    @classmethod
    def _safe_mapping(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            values = value
        elif hasattr(value, "to_dict"):
            values = value.to_dict()
        elif hasattr(value, "__dict__"):
            values = value.__dict__
        else:
            return {"summary": cls._safe_text(value)}
        return {
            str(key): cls._safe(item)
            for key, item in sorted(values.items(), key=lambda pair: str(pair[0]))
            if str(key).lower() not in cls._PRIVATE_KEYS
            and not any(token in str(key).lower() for token in ("chain_of_thought", "scratchpad", "hidden_reasoning"))
        }

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return cls._safe_mapping(value)
        if isinstance(value, (list, tuple, set)):
            return [cls._safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return cls._safe_text(value) if isinstance(value, str) else value
        if hasattr(value, "value"):
            return value.value
        return cls._safe_text(value)

    @staticmethod
    def _safe_text(value: Any) -> str:
        text = str(value or "")
        text = re.sub(r"(?is)(chain[-_ ]of[-_ ]thought|private reasoning|scratchpad)\s*[:=].*$", "[omitted]", text)
        return text[:1000]

    @staticmethod
    def _first(data: Mapping[str, Any], *keys: str) -> str:
        for key in keys:
            if data.get(key):
                return str(data[key])[:500]
        return ""

    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return []
        return sorted({cls._safe_text(item) for item in value if item})

    @staticmethod
    def _bounded(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(1.0, number)), 4)
