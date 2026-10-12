"""
memory_manager.py - Persistent Long-Term Engineering Memory Subsystem for AutoDev

Enables AutoDev to remember previous implementations, architectural decisions,
coding conventions, recurring bugs, reviewer feedback, and execution context
across multiple development cycles and sessions without external vector databases.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# Ensure project root is available on sys.path for direct execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Configure module logger
logger = logging.getLogger("AutoDev.MemoryManager")


class MemoryValidationError(ValueError):
    """
    Raised when a memory entry structure or parameter fails validation rules.
    """
    pass


class MemoryCategory:
    """
    Supported engineering memory categories in AutoDev.
    """
    ARCHITECTURE = "ARCHITECTURE"
    BUG = "BUG"
    DECISION = "DECISION"
    REVIEW = "REVIEW"
    PATTERN = "PATTERN"
    LESSON = "LESSON"
    TODO = "TODO"
    IMPLEMENTATION = "IMPLEMENTATION"
    TESTING = "TESTING"
    OPTIMIZATION = "OPTIMIZATION"
    REFACTORING = "REFACTORING"

    ALL_CATEGORIES: Set[str] = {
        "ARCHITECTURE",
        "BUG",
        "DECISION",
        "REVIEW",
        "PATTERN",
        "LESSON",
        "TODO",
        "IMPLEMENTATION",
        "TESTING",
        "OPTIMIZATION",
        "REFACTORING",
    }

    @classmethod
    def validate(cls, category: str) -> str:
        """
        Validates and normalizes a category string.

        Args:
            category: Raw category string.

        Returns:
            Normalized uppercase category name.

        Raises:
            MemoryValidationError: If the category is unsupported.
        """
        if not category or not isinstance(category, str):
            raise MemoryValidationError("Category must be a non-empty string.")
        normalized = category.strip().upper()
        if normalized not in cls.ALL_CATEGORIES:
            valid_list = ", ".join(sorted(cls.ALL_CATEGORIES))
            raise MemoryValidationError(
                f"Invalid memory category '{category}'. Must be one of: {valid_list}"
            )
        return normalized


@dataclass
class MemoryEntry:
    """
    Represents a single atomic unit of long-term engineering memory.
    """
    id: str
    timestamp: str
    category: str
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    importance: int = 1
    related_tasks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converts memory entry to a serializable dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "tags": list(self.tags),
            "importance": self.importance,
            "related_tasks": list(self.related_tasks),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryEntry:
        """Constructs a MemoryEntry from a dictionary with validation."""
        category = MemoryCategory.validate(data.get("category", ""))
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()
        if not title:
            raise MemoryValidationError("Memory title cannot be empty.")
        if not content:
            raise MemoryValidationError("Memory content cannot be empty.")

        raw_importance = data.get("importance", 1)
        try:
            importance = int(raw_importance)
            if importance < 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise MemoryValidationError(
                f"Importance must be a non-negative integer. Got: {raw_importance!r}"
            )

        return cls(
            id=str(data.get("id", f"mem_{uuid.uuid4().hex[:12]}")),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))),
            category=category,
            title=title,
            content=content,
            tags=[str(t).strip().lower() for t in data.get("tags", []) if str(t).strip()],
            importance=importance,
            related_tasks=[str(t).strip() for t in data.get("related_tasks", []) if str(t).strip()],
        )


@dataclass
class MemorySearchResult:
    """
    Encapsulates a search result entry and its semantic relevance score.
    """
    entry: MemoryEntry
    score: float

    def to_dict(self) -> Dict[str, Any]:
        """Converts search result to a dictionary representation."""
        return {
            "entry": self.entry.to_dict(),
            "score": round(self.score, 4),
        }


@dataclass
class MemoryStatistics:
    """
    Telemetry and aggregations for the memory storage.
    """
    total_entries: int
    categories: Dict[str, int]
    average_importance: float
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None
    latest_update: Optional[str] = None

    def __post_init__(self) -> None:
        if self.newest_entry and not self.latest_update:
            self.latest_update = self.newest_entry
        elif self.latest_update and not self.newest_entry:
            self.newest_entry = self.latest_update

    def to_dict(self) -> Dict[str, Any]:
        """Converts statistics into a clean dictionary."""
        return {
            "total_entries": self.total_entries,
            "categories": self.categories,
            "average_importance": round(self.average_importance, 2),
            "oldest_entry": self.oldest_entry,
            "newest_entry": self.newest_entry,
            "latest_update": self.latest_update or self.newest_entry,
        }


class MemoryManager:
    """
    Persistent Long-Term Memory Manager for AutoDev.
    Provides fast, deterministic semantic scoring, category filtering,
    tag indexing, summarization, and atomic file persistence with
    lazy loading and dirty-flag optimization.
    """

    DEFAULT_MEMORY_PATH = Path("memory/project_memory.json")

    def __init__(
        self,
        memory_path: Union[str, Path] = DEFAULT_MEMORY_PATH,
        auto_create: bool = True,
        persistence_path: Optional[Union[str, Path]] = None,
        lazy_load: bool = True,
    ) -> None:
        """
        Initializes the MemoryManager.

        Args:
            memory_path: Path to the JSON persistence file.
            auto_create: Whether to automatically create an empty memory store if missing.
            persistence_path: Alias for memory_path.
            lazy_load: If True, delays loading until first access.
        """
        target_path = persistence_path or memory_path
        self.memory_path = Path(target_path).resolve()
        self.auto_create = auto_create
        self._entries: Dict[str, MemoryEntry] = {}
        self._loaded = False
        self._dirty = False
        self._last_save_time = 0
        self._save_interval = 5.0  # Batch persistence every 5 seconds if dirty

        if not lazy_load:
            self._ensure_loaded()
        elif not self.memory_path.exists() and self.auto_create:
            self._initialize_empty_store()
            self._loaded = True

    def _ensure_loaded(self) -> None:
        """Triggers lazy loading if not already loaded."""
        if not self._loaded:
            if self.memory_path.exists():
                self.load_memory()
            elif self.auto_create:
                self._initialize_empty_store()
            self._loaded = True

    @property
    def entries(self) -> Dict[str, MemoryEntry]:
        self._ensure_loaded()
        return self._entries

    @property
    def persistence_path(self) -> Path:
        """Alias for memory_path for backward/forward compatibility."""
        return self.memory_path

    # -------------------------------------------------------------------------
    # Core Memory Operations (CRUD)
    # -------------------------------------------------------------------------

    def add_memory(
        self,
        title: str,
        content: str,
        category: str,
        tags: Optional[List[str]] = None,
        importance: int = 1,
        related_tasks: Optional[List[str]] = None,
        entry_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> MemoryEntry:
        """
        Creates, validates, and persists a new memory entry.
        """
        self._ensure_loaded()

        # Validate title
        if not title or not isinstance(title, str) or not title.strip():
            raise MemoryValidationError("Memory title cannot be empty.")

        # Validate content
        if not content or not isinstance(content, str) or not content.strip():
            raise MemoryValidationError("Memory content cannot be empty.")

        # Validate category
        norm_category = MemoryCategory.validate(category)

        # Validate importance
        try:
            imp_int = int(importance)
            if imp_int < 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise MemoryValidationError(
                f"Importance must be a non-negative integer. Got: {importance!r}"
            )

        # Generate or validate ID
        resolved_id = str(entry_id).strip() if entry_id else f"mem_{uuid.uuid4().hex[:12]}"
        if resolved_id in self._entries:
            raise MemoryValidationError(f"Memory with ID '{resolved_id}' already exists.")

        # Resolve timestamp
        resolved_time = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Sanitize tags and tasks
        clean_tags = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
        clean_tasks = [str(t).strip() for t in (related_tasks or []) if str(t).strip()]

        entry = MemoryEntry(
            id=resolved_id,
            timestamp=resolved_time,
            category=norm_category,
            title=title.strip(),
            content=content.strip(),
            tags=clean_tags,
            importance=imp_int,
            related_tasks=clean_tasks,
        )

        self._entries[entry.id] = entry
        self._dirty = True
        self.save_memory(force=True)
        logger.info(f"Added memory entry '{entry.id}' [{entry.category}]: {entry.title}")
        return entry

    def get_memory(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieves a memory entry by its unique ID."""
        self._ensure_loaded()
        return self._entries.get(str(entry_id).strip())

    def update(
        self,
        entry_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: Optional[int] = None,
        related_tasks: Optional[List[str]] = None,
    ) -> MemoryEntry:
        """
        Updates fields of an existing memory entry and persists the store.
        """
        self._ensure_loaded()
        resolved_id = str(entry_id).strip()
        if resolved_id not in self._entries:
            raise KeyError(f"Memory entry '{resolved_id}' not found.")

        entry = self._entries[resolved_id]

        if title is not None:
            if not isinstance(title, str) or not title.strip():
                raise MemoryValidationError("Memory title cannot be empty.")
            entry.title = title.strip()

        if content is not None:
            if not isinstance(content, str) or not content.strip():
                raise MemoryValidationError("Memory content cannot be empty.")
            entry.content = content.strip()

        if category is not None:
            entry.category = MemoryCategory.validate(category)

        if tags is not None:
            entry.tags = [str(t).strip().lower() for t in tags if str(t).strip()]

        if importance is not None:
            try:
                imp_val = int(importance)
                if imp_val < 0:
                    raise ValueError()
                entry.importance = imp_val
            except (ValueError, TypeError):
                raise MemoryValidationError(
                    f"Importance must be a non-negative integer. Got: {importance!r}"
                )

        if related_tasks is not None:
            entry.related_tasks = [str(t).strip() for t in related_tasks if str(t).strip()]

        self._dirty = True
        self.save_memory(force=False)
        logger.info(f"Updated memory entry '{resolved_id}'.")
        return entry

    def delete(self, entry_id: str) -> bool:
        """
        Deletes a memory entry by ID.
        """
        self._ensure_loaded()
        resolved_id = str(entry_id).strip()
        if resolved_id in self._entries:
            del self._entries[resolved_id]
            self._dirty = True
            self.save_memory(force=False)
            logger.info(f"Deleted memory entry '{resolved_id}'.")
            return True
        return False

    def clear(self) -> None:
        """Clears all stored memories and writes empty state to disk."""
        self._ensure_loaded()
        self._entries.clear()
        self._dirty = True
        self.save_memory(force=True)
        logger.info("Cleared all memory entries.")

    # -------------------------------------------------------------------------
    # Deterministic Semantic Search & Retrieval
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[MemorySearchResult]:
        """
        Searches memories using deterministic keyword scoring.
        """
        self._ensure_loaded()
        if not self._entries:
            return []

        # Validate category filter if supplied
        norm_category = MemoryCategory.validate(category) if category else None
        norm_tag = tag.strip().lower() if tag and tag.strip() else None

        # Tokenize search query
        query_text = (query or "").strip().lower()
        query_tokens = self._tokenize(query_text)

        # Collect timestamps for recency calculation
        timestamps = []
        for e in self._entries.values():
            try:
                dt = datetime.fromisoformat(e.timestamp.replace("Z", "+00:00"))
                timestamps.append(dt.timestamp())
            except Exception:
                pass
        max_ts = max(timestamps) if timestamps else time.time()
        min_ts = min(timestamps) if timestamps else time.time()
        ts_range = max(max_ts - min_ts, 1.0)

        results: List[MemorySearchResult] = []

        for entry in self._entries.values():
            # 1. Apply strict filters
            if norm_category and entry.category != norm_category:
                continue
            if norm_tag and norm_tag not in entry.tags:
                continue

            # 2. Compute deterministic semantic score
            score = self._compute_score(entry, query_text, query_tokens, max_ts, ts_range)

            if score >= min_score:
                results.append(MemorySearchResult(entry=entry, score=score))

        # Sort descending by score, then by timestamp descending
        results.sort(key=lambda r: (r.score, r.entry.timestamp), reverse=True)

        return results[:limit]

    def search_by_tag(self, tag: str, limit: Optional[int] = None) -> List[MemoryEntry]:
        """
        Retrieves all memories containing the specified tag.
        """
        self._ensure_loaded()
        norm_tag = str(tag).strip().lower()
        matches = [
            e for e in self._entries.values()
            if norm_tag in e.tags
        ]
        matches.sort(key=lambda e: e.timestamp, reverse=True)
        return matches[:limit] if limit is not None else matches

    def search_by_category(self, category: str, limit: Optional[int] = None) -> List[MemoryEntry]:
        """
        Retrieves all memories belonging to the specified category.
        """
        self._ensure_loaded()
        norm_cat = MemoryCategory.validate(category)
        matches = [
            e for e in self._entries.values()
            if e.category == norm_cat
        ]
        matches.sort(key=lambda e: (e.importance, e.timestamp), reverse=True)
        return matches[:limit] if limit is not None else matches

    def get_memories_by_category(self, category: str, limit: Optional[int] = None) -> List[MemoryEntry]:
        """Alias for search_by_category."""
        return self.search_by_category(category=category, limit=limit)

    def get_by_category(self, category: str, limit: Optional[int] = None) -> List[MemoryEntry]:
        """Alias for search_by_category."""
        return self.search_by_category(category=category, limit=limit)

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        """
        Returns the N most recent memories ordered by timestamp descending.
        """
        self._ensure_loaded()
        all_entries = list(self._entries.values())
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)
        return all_entries[:limit]

    # -------------------------------------------------------------------------
    # Scoring Algorithm Internals
    # -------------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        """Extracts normalized alphanumeric word tokens from text."""
        return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 1]

    def _compute_score(
        self,
        entry: MemoryEntry,
        query_text: str,
        query_tokens: List[str],
        max_ts: float,
        ts_range: float,
    ) -> float:
        """
        Deterministic scoring function.
        """
        if not query_text and not query_tokens:
            # Query-less retrieval: score strictly based on importance and recency
            base_score = 1.0
        else:
            base_score = 0.0

            title_lower = entry.title.lower()
            content_lower = entry.content.lower()
            title_tokens = set(self._tokenize(title_lower))
            content_tokens = set(self._tokenize(content_lower))
            tag_tokens = set(entry.tags)

            # A. Exact phrase matches
            if query_text in title_lower:
                base_score += 4.0
            elif query_text in content_lower:
                base_score += 2.0

            # B. Title token overlap
            if query_tokens:
                title_matches = sum(1 for t in query_tokens if t in title_tokens)
                base_score += (title_matches / len(query_tokens)) * 3.5

            # C. Content token overlap
            if query_tokens:
                content_matches = sum(1 for t in query_tokens if t in content_tokens)
                base_score += (content_matches / len(query_tokens)) * 1.5

            # D. Tag matches
            if query_tokens:
                tag_matches = sum(1 for t in query_tokens if t in tag_tokens)
                base_score += (tag_matches / len(query_tokens)) * 2.5

            # E. Related task match
            for t in query_tokens:
                if any(t in task.lower() for task in entry.related_tasks):
                    base_score += 2.0
                    break

        # If there are no term matches and query was provided, return 0.0
        if query_text and base_score <= 0.0:
            return 0.0

        # F. Importance Bonus (+0.05 per importance unit, max +0.50)
        importance_bonus = min(entry.importance, 10) * 0.05

        # G. Recency Bonus (+0.0 to +0.25)
        recency_bonus = 0.0
        try:
            dt = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))
            ts = dt.timestamp()
            recency_bonus = max(0.0, (ts - (max_ts - ts_range)) / ts_range) * 0.25
        except Exception:
            pass

        return round(base_score + importance_bonus + recency_bonus, 4)

    # -------------------------------------------------------------------------
    # Summarization & Knowledge Synthesis
    # -------------------------------------------------------------------------

    def summarize_project_memory(self) -> Dict[str, List[str]]:
        """
        Generates a structured knowledge summary.
        """
        self._ensure_loaded()
        arch_decisions: List[str] = []
        common_failures: List[str] = []
        conventions: List[str] = []
        unresolved_todos: List[str] = []
        review_comments: List[str] = []

        # Sort entries by importance descending, then timestamp descending
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: (e.importance, e.timestamp),
            reverse=True,
        )

        for entry in sorted_entries:
            summary_bullet = f"[{entry.category}] {entry.title}: {entry.content}"

            if entry.category in (MemoryCategory.ARCHITECTURE, MemoryCategory.DECISION):
                arch_decisions.append(summary_bullet)
            elif entry.category in (MemoryCategory.BUG, MemoryCategory.LESSON):
                common_failures.append(summary_bullet)
            elif entry.category in (MemoryCategory.PATTERN, MemoryCategory.IMPLEMENTATION):
                conventions.append(summary_bullet)
            elif entry.category == MemoryCategory.TODO:
                unresolved_todos.append(summary_bullet)
            elif entry.category in (MemoryCategory.REVIEW, MemoryCategory.TESTING):
                review_comments.append(summary_bullet)

        return {
            "important_architecture_decisions": arch_decisions,
            "common_failures": common_failures,
            "coding_conventions": conventions,
            "unresolved_todos": unresolved_todos,
            "recurring_review_comments": review_comments,
        }

    def format_summary_for_prompt(self, max_items_per_section: int = 5) -> str:
        """
        Formats the project memory summary as a clean markdown block.
        """
        self._ensure_loaded()
        summary = self.summarize_project_memory()
        sections = []

        if summary["important_architecture_decisions"]:
            items = summary["important_architecture_decisions"][:max_items_per_section]
            sections.append("### Key Architectural Decisions\n" + "\n".join(f"- {i}" for i in items))

        if summary["coding_conventions"]:
            items = summary["coding_conventions"][:max_items_per_section]
            sections.append("### Established Coding Conventions & Patterns\n" + "\n".join(f"- {i}" for i in items))

        if summary["common_failures"]:
            items = summary["common_failures"][:max_items_per_section]
            sections.append("### Known Bugs & Lessons Learned\n" + "\n".join(f"- {i}" for i in items))

        if summary["recurring_review_comments"]:
            items = summary["recurring_review_comments"][:max_items_per_section]
            sections.append("### Reviewer Directives & Quality Standards\n" + "\n".join(f"- {i}" for i in items))

        if summary["unresolved_todos"]:
            items = summary["unresolved_todos"][:max_items_per_section]
            sections.append("### Unresolved Engineering TODOs\n" + "\n".join(f"- {i}" for i in items))

        if not sections:
            return "No previous engineering memory recorded."

        return "\n\n".join(sections)

    # -------------------------------------------------------------------------
    # Statistics & Telemetry
    # -------------------------------------------------------------------------

    def statistics(self) -> MemoryStatistics:
        """
        Computes aggregate statistics across all recorded memories.
        """
        self._ensure_loaded()
        total = len(self._entries)
        if total == 0:
            return MemoryStatistics(
                total_entries=0,
                categories={c: 0 for c in sorted(MemoryCategory.ALL_CATEGORIES)},
                average_importance=0.0,
                oldest_entry=None,
                newest_entry=None,
                latest_update=None,
            )

        cat_counts: Dict[str, int] = {c: 0 for c in sorted(MemoryCategory.ALL_CATEGORIES)}
        total_importance = 0
        sorted_by_time = sorted(self._entries.values(), key=lambda e: e.timestamp)

        for e in self._entries.values():
            cat_counts[e.category] = cat_counts.get(e.category, 0) + 1
            total_importance += e.importance

        avg_imp = total_importance / total
        oldest = sorted_by_time[0].timestamp
        newest = sorted_by_time[-1].timestamp

        return MemoryStatistics(
            total_entries=total,
            categories=cat_counts,
            average_importance=avg_imp,
            oldest_entry=oldest,
            newest_entry=newest,
            latest_update=newest,
        )

    # -------------------------------------------------------------------------
    # Import / Export Operations
    # -------------------------------------------------------------------------

    def export_json(self, filepath: Optional[Union[str, Path]] = None) -> str:
        """
        Exports the entire memory database as a JSON string.
        """
        self._ensure_loaded()
        payload = {
            "version": "1.2",
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_entries": len(self._entries),
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        json_str = json.dumps(payload, indent=2, ensure_ascii=False)

        if filepath:
            target = Path(filepath).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json_str, encoding="utf-8")
            logger.info(f"Exported {len(self._entries)} memories to {target}")

        return json_str

    def import_json(
        self,
        filepath_or_json: Union[str, Path],
        overwrite: bool = False,
        merge: bool = True,
    ) -> int:
        """
        Imports memory entries from a JSON string or file path.
        """
        self._ensure_loaded()
        raw_content = ""
        # Check if argument is an existing file
        possible_path = Path(filepath_or_json)
        if possible_path.exists() and possible_path.is_file():
            raw_content = possible_path.read_text(encoding="utf-8")
        else:
            raw_content = str(filepath_or_json)

        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as err:
            raise MemoryValidationError(f"Invalid JSON data for memory import: {err}")

        entries_list: List[Dict[str, Any]] = []
        if isinstance(data, list):
            entries_list = data
        elif isinstance(data, dict):
            entries_list = data.get("entries", [])
            if not entries_list and "id" in data and "title" in data:
                entries_list = [data]
        else:
            raise MemoryValidationError("Import payload must be a JSON object or array.")

        if overwrite:
            self._entries.clear()

        imported_count = 0
        for item in entries_list:
            if not isinstance(item, dict):
                continue
            try:
                entry = MemoryEntry.from_dict(item)
                if not merge and entry.id in self._entries:
                    continue
                self._entries[entry.id] = entry
                imported_count += 1
            except MemoryValidationError as err:
                logger.warning(f"Skipping invalid memory during import: {err}")

        self._dirty = True
        self.save_memory(force=True)
        logger.info(f"Imported {imported_count} memory entries.")
        return imported_count

    # -------------------------------------------------------------------------
    # Persistence & Atomic Recovery
    # -------------------------------------------------------------------------

    def load_memory(self) -> Dict[str, MemoryEntry]:
        """
        Loads and parses the memory store from disk.
        """
        if self._loaded and self._dirty:
            return self._entries

        if not self.memory_path.exists():
            if self.auto_create:
                self._initialize_empty_store()
            return self._entries

        try:
            content = self.memory_path.read_text(encoding="utf-8")
            if not content.strip():
                self._entries = {}
                self._loaded = True
                return self._entries

            raw_data = json.loads(content)
            entries_raw = raw_data.get("entries", []) if isinstance(raw_data, dict) else raw_data

            parsed_entries: Dict[str, MemoryEntry] = {}
            for item in entries_raw:
                if isinstance(item, dict):
                    try:
                        entry = MemoryEntry.from_dict(item)
                        parsed_entries[entry.id] = entry
                    except MemoryValidationError as val_err:
                        logger.warning(f"Skipping malformed entry in {self.memory_path}: {val_err}")

            self._entries = parsed_entries
            self._loaded = True
            self._dirty = False
            logger.info(f"Loaded {len(self._entries)} memories from {self.memory_path}")
            return self._entries

        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as read_err:
            logger.error(f"Memory store at {self.memory_path} is corrupted: {read_err}. Recovering...")
            self._recover_corrupted_store()
            return self._entries

    def save_memory(self, force: bool = True) -> None:
        """
        Atomically writes the memory store to disk.
        Supports delayed batching.
        """
        if not self._dirty and not force:
            return

        now = time.time()
        if not force and (now - self._last_save_time < self._save_interval):
            return

        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": "3.6.1",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_entries": len(self._entries),
            "entries": [e.to_dict() for e in self._entries.values()],
        }

        json_bytes = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")

        # Unique temp file in the same directory
        temp_file = self.memory_path.parent / f"{self.memory_path.stem}.{os.getpid()}.{time.time_ns()}.tmp"

        try:
            with open(temp_file, "wb") as f:
                f.write(json_bytes)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace with retry for Windows
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    os.replace(temp_file, self.memory_path)
                    break
                except (PermissionError, OSError):
                    if attempt == max_retries - 1:
                        shutil.copyfile(temp_file, self.memory_path)
                        try:
                            temp_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                    else:
                        time.sleep(0.02 * (attempt + 1))

            self._dirty = False
            self._last_save_time = now
        except Exception as exc:
            if temp_file.exists():
                try:
                    temp_file.unlink(missing_ok=True)
                except Exception:
                    pass
            raise OSError(f"Failed to atomically persist memory store: {exc}") from exc

    def _initialize_empty_store(self) -> None:
        """Initializes a new empty memory file."""
        self._entries = {}
        self._dirty = False
        self._loaded = True
        self.save_memory(force=True)

    def _recover_corrupted_store(self) -> None:
        """
        Backs up a corrupted memory file and resets to a clean store.
        """
        timestamp = int(time.time())
        corrupted_backup = self.memory_path.parent / f"{self.memory_path.name}.corrupted.{timestamp}.bak"
        try:
            if self.memory_path.exists():
                shutil.copyfile(self.memory_path, corrupted_backup)
                logger.warning(f"Corrupted memory backed up to {corrupted_backup}")
        except Exception as copy_err:
            logger.error(f"Failed to backup corrupted memory file: {copy_err}")

        self._initialize_empty_store()
