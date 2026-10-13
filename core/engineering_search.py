"""Lexical and graph-aware search across engineering memory and code artifacts."""

from __future__ import annotations

import re
from typing import Any, Mapping

from core.engineering_memory import EngineeringMemory
from core.knowledge_graph import KnowledgeGraph
from core.memory_ranking import MemoryRankingEngine
from core.symbol_graph import SymbolGraph


class EngineeringSearchEngine:
    """Search structured history, symbols, and graph entities without external services."""

    def __init__(
        self,
        memory: EngineeringMemory,
        knowledge_graph: KnowledgeGraph | None = None,
        symbol_graph: SymbolGraph | None = None,
        ranking_engine: MemoryRankingEngine | None = None,
    ) -> None:
        self.memory = memory
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()
        self.symbol_graph = symbol_graph
        self.ranking_engine = ranking_engine or MemoryRankingEngine()

    def search(
        self,
        query: str,
        *,
        scope: str | None = None,
        mode: str = "semantic",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must not be negative.")
        if mode not in {"semantic", "lexical", "dependency"}:
            raise ValueError("mode must be 'semantic', 'lexical', or 'dependency'.")
        if mode == "dependency":
            return self._dependency_search(query, limit)
        records = self.memory.search(query, record_type=scope, limit=limit * 2)
        ranked = self.ranking_engine.rank(records, query)
        results = [
            {"kind": "memory", "score": item["ranking_score"], "record": item}
            for item in ranked[:limit]
        ]
        if scope is None or scope in {"module", "package", "class", "function", "pattern", "architecture", "benchmark", "experiment", "learning", "reasoning"}:
            graph_types = scope if scope in {"module", "package", "class", "function", "pattern", "architecture", "benchmark", "experiment", "learning", "reasoning"} else None
            results.extend(
                self._graph_matches(query, graph_types, max(0, limit - len(results)), mode)
            )
        return sorted(
            results,
            key=lambda item: (
                -float(item["score"]),
                str(item.get("record", item.get("node", {})).get("record_id", item.get("node", {}).get("id", ""))),
            ),
        )[:limit]

    def similar(
        self,
        record: Mapping[str, Any] | str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if isinstance(record, Mapping):
            query = _text(record)
            excluded = str(record.get("record_id", record.get("id", "")))
        else:
            query = str(record)
            excluded = str(record)
        return [
            item for item in self.search(query, limit=limit + 1)
            if item.get("record", {}).get("record_id") != excluded
        ][:limit]

    def history(
        self,
        *,
        task_id: str | None = None,
        record_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        records = self.memory.records(record_type)
        if task_id is not None:
            records = [
                item for item in records
                if str(item.get("task_id", "")) == str(task_id)
                or str(task_id) in map(str, item.get("related_tasks", []))
            ]
        return sorted(
            records,
            key=lambda item: (
                str(item.get("timestamp", "")),
                str(item.get("record_id", "")),
            ),
            reverse=True,
        )[:max(0, limit)]

    def recommend(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        candidates = self.search(query, limit=limit * 3)
        successful = []
        for item in candidates:
            record = item.get("record", {})
            if record.get("success") is True or float(record.get("success_rate", 0.0)) > 0.0:
                successful.append(item)
        return successful[:limit]

    def _dependency_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        needle = query.strip()
        if not needle:
            return []
        nodes = self.knowledge_graph.search(needle)
        matched_ids = [item["id"] for item in nodes]
        if self.symbol_graph is not None:
            matched_ids.extend(
                f"module:{path}"
                for path in self.symbol_graph.files
                if needle.casefold() in path.casefold()
            )
        results = []
        for node_id in sorted(set(matched_ids)):
            related = self.knowledge_graph.traverse(
                node_id,
                max_depth=2,
                direction="both",
            )
            results.append({
                "kind": "dependency",
                "node_id": node_id,
                "related_nodes": related,
                "score": 1.0,
            })
        return results[:limit]

    def _graph_matches(
        self,
        query: str,
        node_type: str | None,
        limit: int,
        mode: str,
    ) -> list[dict[str, Any]]:
        if limit == 0:
            return []
        query_tokens = _tokens(query)
        matched = []
        for node in self.knowledge_graph.nodes(node_type):
            text = " ".join((node["name"], node["id"], str(node.get("attributes", {}))))
            haystack = _tokens(text)
            overlap = len(query_tokens & haystack) / len(query_tokens) if query_tokens else 0.0
            phrase = query.casefold() in text.casefold() if query else False
            score = max(overlap, float(phrase))
            if score > 0:
                matched.append({
                    "kind": "graph",
                    "score": round(score, 6),
                    "node": node,
                    "match_mode": mode,
                })
        return sorted(matched, key=lambda item: (-item["score"], item["node"]["id"]))[:limit]


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.casefold()) if len(token) > 1}


def _text(value: Mapping[str, Any]) -> str:
    return " ".join(
        str(value.get(key, ""))
        for key in ("title", "description", "summary", "content", "solution", "root_cause", "type")
    )
