"""Deterministic retrieval and synthesis over prior project knowledge."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from core.reasoning_cache import ReasoningCache


class KnowledgeReasoner:
    """Finds relevant learning records and engineering knowledge by lexical evidence."""

    def __init__(
        self,
        sources: Optional[Iterable[Any]] = None,
        project_root: str | Path = ".",
        cache_manager: Optional[Any] = None,
        cache_root: Optional[str | Path] = None,
    ) -> None:
        self.sources = list(sources or [])
        self.project_root = Path(project_root).resolve()
        self.cache = ReasoningCache("knowledge", self.project_root, cache_manager, cache_root)

    def add_source(self, source: Any) -> None:
        self.sources.append(source)

    def reason(
        self,
        query: str,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        query_terms = self._terms(query)
        sources = self._collect_sources(context)
        key = {"query": query, "context": dict(context or {}), "sources": sources, "limit": limit}
        cached = self.cache.get(key)
        if isinstance(cached, dict):
            return cached
        ranked = []
        for source in sources:
            text = self._render(source)
            terms = self._terms(text)
            overlap = len(query_terms & terms)
            if not overlap:
                continue
            score = overlap / max(1, len(query_terms))
            ranked.append({
                "score": round(score, 4),
                "summary": self._summary(source),
                "source": self._source_name(source),
                "evidence": sorted(query_terms & terms),
            })
        ranked.sort(key=lambda item: (-item["score"], item["source"], item["summary"]))
        result = {
            "query": query,
            "findings": ranked[:max(0, limit)],
            "confidence": round(ranked[0]["score"], 4) if ranked else 0.0,
            "sources_consulted": len(sources),
        }
        self.cache.set(key, result)
        return result

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.reason(query, limit=limit)["findings"]

    def similar_issues(self, issue: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.recall(issue, limit)

    def statistics(self) -> dict[str, int | float]:
        return self.cache.statistics()

    def _collect_sources(self, context: Optional[Mapping[str, Any]]) -> list[Any]:
        values: list[Any] = list(self.sources)
        for key in ("knowledge", "learning_events", "history", "patterns", "reflections"):
            candidate = (context or {}).get(key, [])
            if isinstance(candidate, (list, tuple, set)):
                values.extend(candidate)
            elif candidate:
                values.append(candidate)
        return [self._safe(value) for value in values]

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): cls._safe(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                if not any(token in str(key).lower() for token in ("chain_of_thought", "private_reasoning"))
            }
        if isinstance(value, (list, tuple)):
            return [cls._safe(item) for item in value]
        if hasattr(value, "to_dict"):
            return cls._safe(value.to_dict())
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _render(value: Any) -> str:
        if isinstance(value, Mapping):
            return " ".join(KnowledgeReasoner._render(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return " ".join(KnowledgeReasoner._render(item) for item in value)
        return str(value)

    @classmethod
    def _summary(cls, value: Any) -> str:
        if isinstance(value, Mapping):
            for key in ("summary", "description", "title", "solution", "content"):
                if value.get(key):
                    return str(value[key])[:400]
        return cls._render(value)[:400]

    @staticmethod
    def _source_name(value: Any) -> str:
        if isinstance(value, Mapping):
            return str(value.get("source", value.get("id", value.get("event_id", "memory"))))
        return "memory"

    @staticmethod
    def _terms(value: str) -> set[str]:
        return {
            term for term in re.findall(r"[a-z0-9_]+", str(value).lower())
            if len(term) > 2
        }
