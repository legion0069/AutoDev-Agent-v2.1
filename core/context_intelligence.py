"""Constructs bounded, relevant engineering context from prior experience."""

from __future__ import annotations

from typing import Any, Mapping

from core.experience_engine import ExperienceEngine
from core.memory_ranking import MemoryRankingEngine


class ContextIntelligence:
    """Builds stable context bundles without including private reasoning traces."""

    def __init__(
        self,
        experience_engine: ExperienceEngine,
        ranking_engine: MemoryRankingEngine | None = None,
    ) -> None:
        self.experience_engine = experience_engine
        self.ranking_engine = ranking_engine or MemoryRankingEngine()

    def build_context(
        self,
        task: str | Mapping[str, Any],
        *,
        max_items: int = 8,
        max_chars: int = 6000,
    ) -> dict[str, Any]:
        if max_items < 0 or max_chars < 0:
            raise ValueError("max_items and max_chars must not be negative.")
        records = self.experience_engine.retrieve(task, limit=max_items)
        selected: list[dict[str, Any]] = []
        total_chars = 0
        for record in records:
            item = {
                "record_id": record.get("record_id"),
                "type": record.get("type"),
                "title": record.get("title"),
                "summary": _summary(record),
                "success": record.get("success"),
                "score": record.get("ranking_score", record.get("score", 0.0)),
            }
            size = len(str(item))
            if total_chars + size > max_chars:
                continue
            selected.append(item)
            total_chars += size
        return {
            "query": task if isinstance(task, str) else str(task.get("title", task.get("description", ""))),
            "items": selected,
            "item_count": len(selected),
            "character_count": total_chars,
            "source_ids": [item["record_id"] for item in selected],
        }

    def inject(self, task: Mapping[str, Any], *, max_items: int = 8) -> dict[str, Any]:
        """Return a copy of the task with a named memory context field."""
        result = dict(task)
        result["engineering_memory_context"] = self.build_context(task, max_items=max_items)
        return result


def _summary(record: Mapping[str, Any]) -> str:
    for key in ("summary", "recommendation", "solution", "root_cause", "description"):
        value = record.get(key)
        if value:
            return str(value)
    return str(record.get("content", ""))[:500]
