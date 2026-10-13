"""Persistent, structured long-term engineering memory."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.memory_manager import MemoryManager


_TYPE_CATEGORY = {
    "architecture": "ARCHITECTURE",
    "architecture_decision": "DECISION",
    "bug": "BUG",
    "failure": "BUG",
    "fix": "LESSON",
    "benchmark": "OPTIMIZATION",
    "experiment": "IMPLEMENTATION",
    "learning": "LESSON",
    "reflection": "LESSON",
    "review": "REVIEW",
    "code_review": "REVIEW",
    "plan": "DECISION",
    "task": "IMPLEMENTATION",
    "project": "ARCHITECTURE",
    "refactoring": "REFACTORING",
    "performance": "OPTIMIZATION",
    "report": "IMPLEMENTATION",
}
_SENSITIVE_KEYS = {
    "chain_of_thought",
    "private_reasoning",
    "reasoning_trace",
    "internal_reasoning",
}


class EngineeringMemory:
    """Stores structured engineering records using the existing persistent store."""

    def __init__(
        self,
        project_root: str | Path = ".",
        memory_manager: MemoryManager | None = None,
        *,
        memory_path: str | Path | None = None,
    ) -> None:
        root = Path(project_root).resolve()
        self.memory_manager = memory_manager or MemoryManager(
            memory_path=memory_path or root / "memory" / "engineering_memory.json"
        )

    def store(
        self,
        record: Mapping[str, Any] | str,
        data: Mapping[str, Any] | None = None,
        *,
        record_type: str | None = None,
        record_id: str | None = None,
        title: str | None = None,
        importance: int | None = None,
    ) -> dict[str, Any]:
        """Persist a typed record; equivalent IDs update the existing record."""
        if isinstance(record, str):
            kind = record_type or record
            payload = dict(data or {})
        elif isinstance(record, Mapping):
            payload = dict(record)
            kind = record_type or str(payload.get("type", payload.get("record_type", "implementation")))
        else:
            raise TypeError("record must be a mapping or a record type string.")

        kind = kind.strip().lower().replace("-", "_")
        safe_payload = _safe_mapping(payload)
        safe_payload["type"] = kind
        resolved_title = (title or str(safe_payload.get("title", ""))).strip()
        if not resolved_title:
            resolved_title = f"{kind.replace('_', ' ').title()} record"
        safe_payload.setdefault("title", resolved_title)
        explicit_id = record_id or str(
            safe_payload.get("record_id", safe_payload.get("id", ""))
        ).strip()
        stable_id = explicit_id or _stable_id(kind, safe_payload)
        memory_id = f"eng_{stable_id}"
        content = json.dumps(
            safe_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        category = _TYPE_CATEGORY.get(kind, "IMPLEMENTATION")
        raw_tags = safe_payload.get("tags", [])
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        tags = sorted({
            kind,
            *[str(tag).strip().lower() for tag in raw_tags if str(tag).strip()],
        })
        related_tasks = [
            str(safe_payload.get("task_id"))
        ] if safe_payload.get("task_id") else []
        current = self.memory_manager.get_memory(memory_id)
        if current is None:
            entry = self.memory_manager.add_memory(
                title=resolved_title,
                content=content,
                category=category,
                tags=tags,
                importance=importance if importance is not None else int(safe_payload.get("importance", 5)),
                related_tasks=related_tasks,
                entry_id=memory_id,
                timestamp=str(safe_payload.get("timestamp") or _utc_now()),
            )
        else:
            entry = self.memory_manager.update(
                memory_id,
                title=resolved_title,
                content=content,
                category=category,
                tags=tags,
                importance=importance if importance is not None else int(safe_payload.get("importance", 5)),
                related_tasks=related_tasks,
            )
        return self._decode(entry)

    def retrieve(self, record_id: str) -> dict[str, Any] | None:
        """Retrieve a structured record by its explicit or generated ID."""
        key = str(record_id).strip()
        memory_id = key if key.startswith("eng_") else f"eng_{key}"
        entry = self.memory_manager.get_memory(memory_id)
        return self._decode(entry) if entry is not None else None

    def update(self, record_id: str, changes: Mapping[str, Any]) -> dict[str, Any]:
        """Merge structured fields into an existing record and persist it."""
        if not isinstance(changes, Mapping):
            raise TypeError("changes must be a mapping.")
        existing = self.retrieve(record_id)
        if existing is None:
            raise KeyError(f"Engineering memory record {record_id!r} not found.")
        merged = {**existing, **_safe_mapping(changes)}
        return self.store(
            merged,
            record_type=str(merged["type"]),
            record_id=str(existing["record_id"]),
            title=str(merged.get("title", existing["title"])),
        )

    def search(
        self,
        query: str = "",
        *,
        record_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search records deterministically, optionally restricting record type."""
        if limit < 0:
            raise ValueError("limit must not be negative.")
        category = _TYPE_CATEGORY.get(record_type.strip().lower().replace("-", "_")) if record_type else None
        results = self.memory_manager.search(
            query,
            category=category,
            limit=max(limit * 3, limit),
        )
        records = []
        for result in results:
            record = self._decode(result.entry)
            if record_type and record.get("type") != record_type.strip().lower().replace("-", "_"):
                continue
            record["score"] = result.score
            records.append(record)
        return sorted(
            records,
            key=lambda item: (-float(item["score"]), str(item["record_id"])),
        )[:limit]

    def records(self, record_type: str | None = None) -> list[dict[str, Any]]:
        """Return all structured records in stable ID order."""
        entries = self.memory_manager.entries.values()
        records = [self._decode(item) for item in entries]
        if record_type:
            kind = record_type.strip().lower().replace("-", "_")
            records = [item for item in records if item.get("type") == kind]
        return sorted(records, key=lambda item: str(item["record_id"]))

    def forget(self, record_id: str) -> bool:
        """Delete an explicitly identified memory record."""
        key = str(record_id).strip()
        memory_id = key if key.startswith("eng_") else f"eng_{key}"
        return self.memory_manager.delete(memory_id)

    def summarize(self, *, record_type: str | None = None) -> dict[str, Any]:
        records = self.records(record_type)
        counts: dict[str, int] = {}
        for record in records:
            kind = str(record.get("type", "implementation"))
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "total_records": len(records),
            "records_by_type": dict(sorted(counts.items())),
            "record_ids": [str(item["record_id"]) for item in records],
        }

    @staticmethod
    def _decode(entry: Any) -> dict[str, Any]:
        try:
            payload = json.loads(entry.content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Stored engineering memory {entry.id!r} is malformed.") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Stored engineering memory {entry.id!r} is not a JSON object.")
        payload["record_id"] = entry.id.removeprefix("eng_")
        payload.setdefault("type", entry.category.lower())
        payload.setdefault("title", entry.title)
        payload.setdefault("timestamp", entry.timestamp)
        return payload


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    def sanitize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                str(key): sanitize(child)
                for key, child in sorted(item.items(), key=lambda pair: str(pair[0]))
                if str(key).casefold() not in _SENSITIVE_KEYS
            }
        if isinstance(item, (list, tuple)):
            return [sanitize(child) for child in item]
        if isinstance(item, set):
            return sorted((sanitize(child) for child in item), key=str)
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        if callable(getattr(item, "to_dict", None)):
            return sanitize(item.to_dict())
        return str(item)

    return sanitize(value)


def _stable_id(*parts: Any) -> str:
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
