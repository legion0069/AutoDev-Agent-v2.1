"""Coordinates persistent memory capabilities for optional orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.context_intelligence import ContextIntelligence
from core.documentation_intelligence import DocumentationIntelligence
from core.engineering_memory import EngineeringMemory
from core.engineering_search import EngineeringSearchEngine
from core.experience_engine import ExperienceEngine
from core.knowledge_consolidation import KnowledgeConsolidationEngine
from core.knowledge_graph import KnowledgeGraph
from core.memory_ranking import MemoryRankingEngine
from core.recommendation_engine import RecommendationEngine


class MemoryController:
    """Unified facade for memory recording, retrieval, graphing, and reporting."""

    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        memory: EngineeringMemory | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.memory = memory or EngineeringMemory(self.project_root)
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()
        self.ranking = MemoryRankingEngine()
        self.search_engine = EngineeringSearchEngine(
            self.memory,
            self.knowledge_graph,
            ranking_engine=self.ranking,
        )
        self.experience = ExperienceEngine(self.memory, self.search_engine, self.ranking)
        self.context = ContextIntelligence(self.experience, self.ranking)
        self.consolidation = KnowledgeConsolidationEngine(self.memory)
        self.recommendations = RecommendationEngine(self.memory, self.search_engine, self.ranking)
        self.documentation = DocumentationIntelligence(
            self.project_root,
            self.memory,
            self.knowledge_graph,
        )

    def record_task_outcome(self, outcome: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(outcome, Mapping):
            raise TypeError("outcome must be a mapping.")
        record = dict(outcome)
        record.setdefault("type", "task")
        if not isinstance(record.get("success"), bool):
            raise ValueError("Task outcome must include a boolean success field.")
        stored = self.memory.store(record)
        self._add_memory_node(stored)
        return stored

    def record(self, record: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        stored = self.memory.store(record, **kwargs)
        self._add_memory_node(stored)
        return stored

    def retrieve_context(self, task: str | Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self.context.build_context(task, **kwargs)

    def search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return self.search_engine.search(query, **kwargs)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "memory": self.memory.summarize(),
            "knowledge_graph": {
                "nodes": len(self.knowledge_graph.nodes()),
                "edges": len(self.knowledge_graph.edges()),
            },
        }

    def consolidate(self, *, min_occurrences: int = 2, persist: bool = False) -> list[dict[str, Any]]:
        return self.consolidation.consolidate(
            min_occurrences=min_occurrences,
            persist=persist,
        )

    def _add_memory_node(self, record: Mapping[str, Any]) -> None:
        record_id = str(record["record_id"])
        node_id = f"memory:{record_id}"
        self.knowledge_graph.add_node(
            "memory",
            node_id,
            str(record.get("title", record_id)),
            {
                "record_id": record_id,
                "type": record.get("type"),
                "task_id": record.get("task_id"),
                "success": record.get("success"),
            },
        )
        task_id = record.get("task_id")
        if task_id:
            task_node_id = f"task:{task_id}"
            if self.knowledge_graph.get_node(task_node_id) is None:
                self.knowledge_graph.add_node("task", task_node_id, str(task_id))
            self.knowledge_graph.add_edge(task_node_id, node_id, "has_outcome")
