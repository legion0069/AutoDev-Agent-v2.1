"""Coordinates one deterministic environment-awareness report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.api_discovery import APIDiscoveryEngine
from core.dependency_intelligence import DependencyIntelligence
from core.documentation_intelligence import DocumentationIntelligence
from core.environment_analyzer import EnvironmentAnalyzer
from core.git_intelligence import GitIntelligence
from core.knowledge_graph import KnowledgeGraph
from core.repository_intelligence import RepositoryIntelligence
from core.symbol_graph import SymbolGraph
from core.tool_execution_planner import ToolExecutionPlanner
from core.tool_registry import ToolRegistry
from core.tool_selector import ToolSelector


class EnvironmentController:
    """Coordinates host, repository, Git, dependency, API, docs, and tool insights."""

    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        tool_registry: ToolRegistry | None = None,
        git_intelligence: GitIntelligence | None = None,
        environment_analyzer: EnvironmentAnalyzer | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.environment_analyzer = environment_analyzer or EnvironmentAnalyzer(self.project_root)
        self.repository_intelligence = RepositoryIntelligence(self.project_root)
        self.git_intelligence = git_intelligence or GitIntelligence(self.project_root)
        self.dependency_intelligence = DependencyIntelligence(self.project_root)
        self.api_discovery = APIDiscoveryEngine(self.project_root)
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()
        self.documentation_intelligence = DocumentationIntelligence(
            self.project_root,
            knowledge_graph=self.knowledge_graph,
        )
        self.tool_registry = tool_registry or ToolRegistry(discover=True)
        self.tool_selector = ToolSelector(self.tool_registry)
        self.execution_planner = ToolExecutionPlanner(self.tool_selector)
        self.latest_report: dict[str, Any] | None = None

    def analyze(
        self,
        *,
        symbol_graph: SymbolGraph | None = None,
        task: str = "Analyze repository and select appropriate development tools",
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a report in a fixed order; this method never executes selected tools."""
        environment = self.environment_analyzer.analyze()
        repository = self.repository_intelligence.analyze(symbol_graph)
        dependencies = self.dependency_intelligence.analyze(symbol_graph)
        git = self.git_intelligence.analyze()
        tools = self.tool_registry.to_dict()
        recommendations = self.tool_selector.recommend(
            task,
            environment=environment,
            repository=repository,
            history=history or [],
        )
        apis = self.api_discovery.discover()
        docs = self.documentation_intelligence.analyze()
        documentation_v2 = self.documentation_intelligence.analyze_v2(
            sections=docs,
            api_metadata=apis,
        )
        plan = self.execution_planner.plan(
            task,
            environment=environment,
            repository=repository,
        )
        self.latest_report = {
            "version": "3.11",
            "environment": environment,
            "repository": repository,
            "dependencies": dependencies,
            "git": git,
            "tools": tools,
            "tool_recommendations": recommendations,
            "apis": apis,
            "documentation": documentation_v2,
            "execution_plan": plan,
            "execution_performed": False,
        }
        return self.latest_report

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "report_available": self.latest_report is not None,
            "tool_count": len(self.tool_registry.list_tools()),
            "latest_report": self.latest_report,
        }
