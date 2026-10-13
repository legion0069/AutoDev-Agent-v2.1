"""Indexes documentation and links it to engineering knowledge."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from core.engineering_memory import EngineeringMemory
from core.knowledge_graph import KnowledgeGraph


class DocumentationIntelligence:
    """Extracts stable documentation sections and connects them to memories."""

    def __init__(
        self,
        project_root: str | Path = ".",
        memory: EngineeringMemory | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.memory = memory
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()

    def analyze(self, paths: Iterable[str | Path] | None = None) -> list[dict[str, Any]]:
        targets = (
            [self.project_root / path for path in paths]
            if paths is not None
            else sorted(self.project_root.glob("**/*.md"))
        )
        results = []
        for path in sorted({Path(item).resolve() for item in targets}, key=str):
            if not path.is_file() or not path.is_relative_to(self.project_root):
                continue
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(self.project_root).as_posix()
            for section in _sections(text):
                section_id = hashlib.sha256(
                    f"{relative}\0{section['heading']}".encode("utf-8")
                ).hexdigest()[:20]
                item = {
                    "path": relative,
                    "heading": section["heading"],
                    "level": section["level"],
                    "summary": " ".join(section["content"].split())[:1000],
                    "content_hash": hashlib.sha256(section["content"].encode("utf-8")).hexdigest(),
                    "section_id": section_id,
                }
                node_id = f"documentation:{section_id}"
                self.knowledge_graph.add_node(
                    "documentation",
                    node_id,
                    section["heading"],
                    item,
                )
                results.append(item)
        return results

    def analyze_v2(
        self,
        *,
        sections: list[dict[str, Any]] | None = None,
        api_metadata: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Add README, changelog, architecture, API, and link intelligence."""
        documents = sections if sections is not None else self.analyze()
        apis = (
            [dict(item) for item in api_metadata]
            if api_metadata is not None
            else []
        )
        references = []
        for relative in sorted({str(item["path"]) for item in documents}):
            path = self.project_root / relative
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            for target in sorted(set(_markdown_references(text))):
                references.append({"source": relative, "target": target})

        def sections_for(names: set[str]) -> list[dict[str, Any]]:
            return [
                dict(section) for section in documents
                if Path(str(section["path"])).name.casefold() in names
            ]

        architecture = [
            dict(section) for section in documents
            if any(
                term in str(section["path"]).casefold()
                or term in str(section["heading"]).casefold()
                for term in ("architecture", "system-design", "system_design")
            )
        ]
        return {
            "sections": documents,
            "readme": sections_for({"readme.md", "readme.mdx", "readme.rst"}),
            "changelog": sections_for({
                "changelog.md", "changelog.mdx", "changes.md", "history.md",
            }),
            "architecture_documents": architecture,
            "api_metadata": sorted(
                apis,
                key=lambda item: (
                    str(item.get("kind", "")),
                    str(item.get("path", "")),
                    str(item.get("name", "")),
                ),
            ),
            "cross_references": references,
        }

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        api_metadata: Iterable[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must not be negative.")
        needle = query.casefold().strip()
        matches = []
        for node in self.knowledge_graph.nodes("documentation"):
            attrs = node["attributes"]
            haystack = f"{node['name']} {attrs.get('path', '')} {attrs.get('summary', '')}".casefold()
            if needle in haystack:
                matches.append({
                    "heading": node["name"],
                    "path": attrs["path"],
                    "summary": attrs["summary"],
                    "section_id": attrs["section_id"],
                })
        if api_metadata is not None and needle:
            for api in api_metadata:
                text = " ".join(str(value) for value in api.values()).casefold()
                if needle in text:
                    matches.append({
                        "kind": "api",
                        "heading": str(api.get("name", "")),
                        "path": str(api.get("path", "")),
                        "summary": text[:1000],
                        "section_id": "",
                    })
        return sorted(
            matches,
            key=lambda item: (item["path"], item["heading"], item.get("kind", "documentation")),
        )[:limit]

    def link_memories(self) -> int:
        if self.memory is None:
            return 0
        linked = 0
        docs = self.knowledge_graph.nodes("documentation")
        for record in self.memory.records():
            phrases = _terms(record)
            for doc in docs:
                attrs = doc["attributes"]
                text = f"{doc['name']} {attrs.get('summary', '')}".casefold()
                if any(term in text for term in phrases if len(term) > 3):
                    memory_node = f"memory:{record['record_id']}"
                    if self.knowledge_graph.get_node(memory_node) is None:
                        self.knowledge_graph.add_node(
                            "memory",
                            memory_node,
                            str(record.get("title", record["record_id"])),
                            {"record_id": record["record_id"], "type": record.get("type")},
                        )
                    self.knowledge_graph.add_edge(memory_node, doc["id"], "documented_by")
                    linked += 1
        return linked


def _sections(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    heading = ""
    level = 0
    content: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            if heading:
                sections.append({"heading": heading, "level": level, "content": "\n".join(content)})
            heading, level, content = match.group(2), len(match.group(1)), []
        elif heading:
            content.append(line)
    if heading:
        sections.append({"heading": heading, "level": level, "content": "\n".join(content)})
    return sections


def _terms(record: dict[str, Any]) -> set[str]:
    values = [str(record.get(key, "")) for key in ("title", "summary", "description", "recommendation")]
    return set(re.findall(r"[a-z0-9_]+", " ".join(values).casefold()))


def _markdown_references(text: str) -> list[str]:
    inline = re.findall(r"\[[^\]]+\]\(([^)\s]+)(?:\s+[^)]*)?\)", text)
    reference_definitions = re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(\S+)", text)
    return inline + reference_definitions
