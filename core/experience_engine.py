"""Retrieves reusable engineering experience from persistent task outcomes."""

from __future__ import annotations

from typing import Any, Mapping

from core.engineering_memory import EngineeringMemory
from core.engineering_search import EngineeringSearchEngine
from core.memory_ranking import MemoryRankingEngine


class ExperienceEngine:
    """Finds prior implementations, failures, fixes, and architectural decisions."""

    def __init__(
        self,
        memory: EngineeringMemory,
        search_engine: EngineeringSearchEngine | None = None,
        ranking_engine: MemoryRankingEngine | None = None,
    ) -> None:
        self.memory = memory
        self.search_engine = search_engine or EngineeringSearchEngine(memory)
        self.ranking_engine = ranking_engine or MemoryRankingEngine()

    def retrieve(
        self,
        task: str | Mapping[str, Any],
        *,
        limit: int = 10,
        include_failures: bool = True,
    ) -> list[dict[str, Any]]:
        query = task if isinstance(task, str) else " ".join(
            str(task.get(key, ""))
            for key in ("title", "description", "goal", "task_type", "files")
        )
        candidates = self.search_engine.search(query, limit=max(limit * 3, limit))
        records = []
        for result in candidates:
            record = result.get("record")
            if not isinstance(record, dict):
                continue
            if not include_failures and record.get("success") is False:
                continue
            records.append({**record, "score": result["score"]})
        return self.ranking_engine.best_memories(records, query, limit=limit)

    def similar_tasks(self, task: Mapping[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
        candidates = self.retrieve(task, limit=limit * 3)
        task_id = str(task.get("task_id", task.get("id", "")))
        return [
            item for item in candidates
            if str(item.get("task_id", item.get("record_id", ""))) != task_id
        ][:limit]

    def successful_patterns(self, query: str = "", *, limit: int = 10) -> list[dict[str, Any]]:
        candidates = self.retrieve(query, limit=limit * 3, include_failures=False)
        return [
            item for item in candidates
            if item.get("success") is True or float(item.get("success_rate", 0.0)) > 0
        ][:limit]

    def failure_lessons(self, query: str = "", *, limit: int = 10) -> list[dict[str, Any]]:
        candidates = self.retrieve(query, limit=limit * 3)
        return [
            item for item in candidates
            if item.get("success") is False or item.get("type") in {"bug", "failure"}
        ][:limit]
