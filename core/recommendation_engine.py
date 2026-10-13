"""Produces deterministic engineering recommendations from project history."""

from __future__ import annotations

from typing import Any, Mapping

from core.engineering_memory import EngineeringMemory
from core.engineering_search import EngineeringSearchEngine
from core.memory_ranking import MemoryRankingEngine


class RecommendationEngine:
    """Ranks evidence-backed recommendations from engineering records."""

    def __init__(
        self,
        memory: EngineeringMemory,
        search_engine: EngineeringSearchEngine | None = None,
        ranking_engine: MemoryRankingEngine | None = None,
    ) -> None:
        self.memory = memory
        self.search_engine = search_engine or EngineeringSearchEngine(memory)
        self.ranking_engine = ranking_engine or MemoryRankingEngine()

    def recommend(
        self,
        context: str | Mapping[str, Any] = "",
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must not be negative.")
        query = context if isinstance(context, str) else " ".join(
            str(context.get(key, "")) for key in ("goal", "task", "summary", "files")
        )
        matches = self.search_engine.search(query, limit=max(limit * 4, limit))
        recommendations = []
        seen = set()
        for match in matches:
            record = match.get("record")
            if not isinstance(record, dict):
                continue
            suggestion = record.get("recommendation", record.get("solution"))
            if not suggestion:
                continue
            normalized = str(suggestion).strip()
            if not normalized or normalized.casefold() in seen:
                continue
            seen.add(normalized.casefold())
            recommendations.append({
                "recommendation": normalized,
                "source_record_id": record.get("record_id"),
                "source_type": record.get("type"),
                "confidence": float(record.get("confidence", match.get("score", 0.0))),
                "success": record.get("success"),
                "score": float(match.get("score", 0.0)),
                "evidence": _evidence(record),
            })
        return sorted(
            recommendations,
            key=lambda item: (-item["score"], -item["confidence"], str(item["source_record_id"])),
        )[:limit]

    def recommend_for_task(
        self,
        task: Mapping[str, Any],
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self.recommend(task, limit=limit)


def _evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in ("task_id", "timestamp", "success", "benchmark", "review")
        if key in record
    }
