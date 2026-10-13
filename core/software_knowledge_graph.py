"""Deterministic graph of code structure and engineering evolution artifacts."""

from __future__ import annotations

import json
from copy import deepcopy
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from core.symbol_graph import SymbolGraph


class SoftwareKnowledgeGraph:
    """Stores typed software entities with stable, deterministic traversal."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: set[tuple[str, str, str]] = set()

    def add_node(
        self,
        node_type: str,
        node_id: str,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not node_type.strip() or not node_id.strip():
            raise ValueError("node_type and node_id must be non-empty.")
        node = {
            "id": node_id,
            "type": node_type,
            "name": name,
            "attributes": deepcopy(attributes or {}),
        }
        self._nodes[node_id] = node
        return deepcopy(node)

    def add_edge(self, source_id: str, target_id: str, relation: str) -> None:
        if source_id not in self._nodes or target_id not in self._nodes:
            raise KeyError(f"Both edge endpoints must exist: {source_id!r} -> {target_id!r}.")
        if not relation.strip():
            raise ValueError("relation must be non-empty.")
        self._edges.add((source_id, target_id, relation))

    def add_repository(
        self,
        symbol_graph: SymbolGraph,
        *,
        architectures: Iterable[dict[str, Any]] = (),
        patterns: Iterable[dict[str, Any]] = (),
    ) -> None:
        modules = sorted(symbol_graph.files)
        for path in modules:
            self.add_node("module", f"module:{path}", path, {"path": path})
        for symbol in sorted(symbol_graph.symbols.values(), key=lambda item: item.id):
            module_id = f"module:{symbol.file}"
            self.add_node(
                self._symbol_type(symbol.symbol_type),
                f"symbol:{symbol.id}",
                symbol.name,
                {
                    "qualified_name": symbol.qualified_name,
                    "file": symbol.file,
                    "line": symbol.line,
                },
            )
            if module_id in self._nodes:
                self.add_edge(module_id, f"symbol:{symbol.id}", "defines")
        for dependency in sorted(
            symbol_graph.dependencies,
            key=lambda item: (item.source_file, item.target_file, item.dependency_type),
        ):
            source_id = f"module:{dependency.source_file}"
            target_id = f"module:{dependency.target_file}"
            if source_id in self._nodes and target_id in self._nodes:
                self.add_edge(source_id, target_id, "depends_on")
        for architecture in sorted(architectures, key=lambda item: str(item.get("pattern_name", ""))):
            name = str(architecture.get("pattern_name", architecture.get("name", "architecture")))
            node_id = f"architecture:{name}"
            self.add_node("architecture", node_id, name, architecture)
        for pattern in sorted(patterns, key=lambda item: (str(item.get("kind", "")), str(item.get("location", "")))):
            name = str(pattern.get("kind", "pattern"))
            node_id = f"pattern:{pattern.get('location', name)}"
            self.add_node("pattern", node_id, name, pattern)

    def add_artifact(self, artifact_type: str, artifact_id: str, name: str, data: dict[str, Any]) -> None:
        self.add_node(artifact_type, f"{artifact_type}:{artifact_id}", name, data)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        node = self._nodes.get(node_id)
        return deepcopy(node) if node is not None else None

    def nodes(self, node_type: str | None = None) -> list[dict[str, Any]]:
        selected = (
            node for node in self._nodes.values()
            if node_type is None or node["type"] == node_type
        )
        return [deepcopy(node) for node in sorted(selected, key=lambda item: item["id"])]

    def edges(self) -> list[dict[str, str]]:
        return [
            {"source": source, "target": target, "relation": relation}
            for source, target, relation in sorted(self._edges)
        ]

    def neighbors(self, node_id: str, direction: str = "outgoing") -> list[str]:
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be 'outgoing', 'incoming', or 'both'.")
        if node_id not in self._nodes:
            return []
        neighbors = set()
        for source, target, _ in self._edges:
            if direction in {"outgoing", "both"} and source == node_id:
                neighbors.add(target)
            if direction in {"incoming", "both"} and target == node_id:
                neighbors.add(source)
        return sorted(neighbors)

    def traverse(
        self,
        start_node_id: str,
        *,
        max_depth: int = 1,
        direction: str = "outgoing",
    ) -> list[str]:
        if max_depth < 0:
            raise ValueError("max_depth must not be negative.")
        if start_node_id not in self._nodes:
            return []
        visited = {start_node_id}
        queue = deque([(start_node_id, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in self.neighbors(current, direction):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
        visited.remove(start_node_id)
        return sorted(visited)

    def shortest_path(self, start_node_id: str, end_node_id: str) -> list[str] | None:
        if start_node_id not in self._nodes or end_node_id not in self._nodes:
            return None
        queue = deque([[start_node_id]])
        visited = {start_node_id}
        while queue:
            path = queue.popleft()
            if path[-1] == end_node_id:
                return path
            for neighbor in self.neighbors(path[-1]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def search(self, query: str, node_type: str | None = None) -> list[dict[str, Any]]:
        needle = query.casefold()
        return [
            node for node in self.nodes(node_type)
            if needle in node["name"].casefold()
            or needle in node["id"].casefold()
        ]

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes(), "edges": self.edges()}

    def export_json(self, output_path: str | Path | None = None) -> str:
        content = json.dumps(self.to_dict(), indent=2, sort_keys=True)
        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return content

    @staticmethod
    def _symbol_type(value: str) -> str:
        normalized = str(value).casefold()
        if "class" in normalized or "interface" in normalized:
            return "class"
        if "method" in normalized:
            return "function"
        return "function"
