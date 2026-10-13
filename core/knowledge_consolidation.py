"""Consolidates repeated engineering outcomes into stable knowledge summaries."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable, Mapping

from core.engineering_memory import EngineeringMemory


class KnowledgeConsolidationEngine:
    """Deduplicates and summarizes recurring records without deleting source evidence."""

    def __init__(self, memory: EngineeringMemory) -> None:
        self.memory = memory

    def consolidate(
        self,
        records: Iterable[Mapping[str, Any]] | None = None,
        *,
        min_occurrences: int = 2,
        persist: bool = False,
    ) -> list[dict[str, Any]]:
        if min_occurrences < 1:
            raise ValueError("min_occurrences must be at least 1.")
        source = list(records) if records is not None else self.memory.records()
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in source:
            item = dict(record)
            if item.get("type") == "consolidated_knowledge":
                continue
            key = _fingerprint(item)
            groups[key].append(item)
        consolidated = []
        for fingerprint, group in sorted(groups.items()):
            if len(group) < min_occurrences:
                continue
            ordered = sorted(group, key=lambda item: str(item.get("record_id", "")))
            summary = {
                "type": "consolidated_knowledge",
                "title": str(ordered[0].get("title", "Repeated engineering knowledge")),
                "topic": str(ordered[0].get("topic", ordered[0].get("type", "engineering"))),
                "occurrences": len(ordered),
                "source_record_ids": [str(item.get("record_id", "")) for item in ordered],
                "source_types": sorted({str(item.get("type", "implementation")) for item in ordered}),
                "successful_occurrences": sum(item.get("success") is True for item in ordered),
                "failed_occurrences": sum(item.get("success") is False for item in ordered),
                "fingerprint": fingerprint,
            }
            if persist:
                summary = self.memory.store(summary, record_id=f"consolidated-{fingerprint}")
            consolidated.append(summary)
        return consolidated

    def deduplicate(
        self,
        records: Iterable[Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        source = list(records) if records is not None else self.memory.records()
        unique: dict[str, dict[str, Any]] = {}
        for record in source:
            if record.get("type") == "consolidated_knowledge":
                continue
            fingerprint = _fingerprint(record)
            unique.setdefault(fingerprint, dict(record))
        return [unique[key] for key in sorted(unique)]


def _fingerprint(record: Mapping[str, Any]) -> str:
    material = {
        key: record.get(key)
        for key in (
            "type",
            "topic",
            "title",
            "problem",
            "description",
            "summary",
            "solution",
            "root_cause",
            "recommendation",
        )
        if record.get(key) is not None
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
