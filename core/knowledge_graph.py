"""Deterministic engineering knowledge graph built on AutoDev's SymbolGraph."""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable

from core.software_knowledge_graph import SoftwareKnowledgeGraph
from core.symbol_graph import SymbolGraph


class KnowledgeGraph(SoftwareKnowledgeGraph):
    """Adds stable multi-path and dependency views to the V4 knowledge graph."""

    def add_repository(
        self,
        symbol_graph: SymbolGraph,
        *,
        project_id: str | None = None,
        architectures: Iterable[dict[str, Any]] = (),
        patterns: Iterable[dict[str, Any]] = (),
    ) -> None:
        super().add_repository(
            symbol_graph,
            architectures=architectures,
            patterns=patterns,
        )
        if project_id:
            project_node = f"project:{project_id}"
            self.add_node("project", project_node, project_id, {"project_id": project_id})
            for module in sorted(symbol_graph.files):
                self.add_edge(project_node, f"module:{module}", "contains")

        for module in sorted(symbol_graph.files):
            package = module.rpartition("/")[0]
            if not package:
                continue
            package_id = f"package:{package}"
            self.add_node("package", package_id, package, {"path": package})
            self.add_edge(package_id, f"module:{module}", "contains")

    def find_paths(
        self,
        start_node_id: str,
        end_node_id: str,
        *,
        max_depth: int = 5,
        max_paths: int = 20,
    ) -> list[list[str]]:
        """Return bounded simple paths, ordered lexicographically by node IDs."""
        if max_depth < 0:
            raise ValueError("max_depth must not be negative.")
        if max_paths < 0:
            raise ValueError("max_paths must not be negative.")
        if max_paths == 0 or start_node_id not in self._nodes or end_node_id not in self._nodes:
            return []
        if start_node_id == end_node_id:
            return [[start_node_id]]
        paths: list[list[str]] = []
        queue = deque([[start_node_id]])
        while queue and len(paths) < max_paths:
            path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue
            for neighbor in self.neighbors(path[-1]):
                if neighbor in path:
                    continue
                extended = path + [neighbor]
                if neighbor == end_node_id:
                    paths.append(extended)
                else:
                    queue.append(extended)
        return sorted(paths, key=lambda path: (len(path), path))

    def related_nodes(
        self,
        node_id: str,
        *,
        max_depth: int = 1,
        direction: str = "both",
        node_type: str | None = None,
    ) -> list[dict[str, Any]]:
        ids = self.traverse(node_id, max_depth=max_depth, direction=direction)
        nodes = [self.get_node(item) for item in ids]
        return [
            item for item in nodes
            if item is not None and (node_type is None or item["type"] == node_type)
        ]

    def dependency_graph(self, node_id: str | None = None) -> dict[str, list[str]]:
        """Return the directed module/package dependency adjacency map."""
        edges = self.edges()
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            if edge["relation"] not in {"depends_on", "dependency", "depends"}:
                continue
            source = edge["source"]
            target = edge["target"]
            if node_id is not None and source != node_id:
                continue
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set())
        if node_id is not None and node_id in self._nodes:
            adjacency.setdefault(node_id, set())
        return {
            key: sorted(values)
            for key, values in sorted(adjacency.items())
        }
