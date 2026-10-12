"""Deterministic repository change detection for incremental AutoDev workflows."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Set

logger = logging.getLogger("AutoDev.ChangeDetector")


@dataclass
class ChangeSet:
    """Classified repository changes between two content-hash snapshots."""

    modified_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    renamed_files: Dict[str, str] = field(default_factory=dict)
    new_files: list[str] = field(default_factory=list)
    changed_tests: list[str] = field(default_factory=list)
    changed_documentation: list[str] = field(default_factory=list)
    current_snapshot: Dict[str, str] = field(default_factory=dict)

    @property
    def changed_files(self) -> list[str]:
        """Returns all paths affected by this change, in stable order."""
        paths = set(self.modified_files) | set(self.deleted_files) | set(self.new_files)
        for old_path, new_path in self.renamed_files.items():
            paths.update((old_path, new_path))
        return sorted(paths)

    @property
    def changed_source_files(self) -> list[str]:
        """Returns changed, existing paths suitable for indexing."""
        paths = set(self.modified_files) | set(self.new_files)
        paths.update(self.renamed_files.values())
        return sorted(paths)

    def to_dict(self) -> Dict[str, object]:
        return {
            "modified_files": list(self.modified_files),
            "deleted_files": list(self.deleted_files),
            "renamed_files": dict(sorted(self.renamed_files.items())),
            "new_files": list(self.new_files),
            "changed_tests": list(self.changed_tests),
            "changed_documentation": list(self.changed_documentation),
            "current_snapshot": dict(sorted(self.current_snapshot.items())),
        }


class RepositoryChangeDetector:
    """Hashes repository files and compares them with a persisted prior snapshot."""

    VERSION = 1
    DEFAULT_IGNORED_DIRS = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        "target",
    }
    DOCUMENTATION_SUFFIXES = {".md", ".rst", ".adoc", ".txt"}

    def __init__(
        self,
        project_root: str | Path,
        snapshot_path: Optional[str | Path] = None,
        ignored_dirs: Optional[Set[str]] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.snapshot_path = (
            Path(snapshot_path).resolve()
            if snapshot_path is not None
            else self.project_root / "memory" / "cache" / "repository_changes" / "snapshot.json"
        )
        self.ignored_dirs = set(ignored_dirs or self.DEFAULT_IGNORED_DIRS)
        self.ignored_dirs.add("__pycache__")
        self.current_snapshot: Dict[str, str] = {}
        self.current_file_stats: Dict[str, tuple[int, int, int, int]] = {}

    def snapshot(self) -> Dict[str, str]:
        """Returns normalized relative paths and SHA-256 hashes for regular files."""
        hashes: Dict[str, str] = {}
        file_stats: Dict[str, tuple[int, int, int, int]] = {}
        if not self.project_root.is_dir():
            self.current_snapshot = {}
            self.current_file_stats = {}
            return hashes

        for current_root, directories, file_names in os.walk(self.project_root):
            current_path = Path(current_root)
            rel_root = current_path.relative_to(self.project_root)
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in self.ignored_dirs
                and (
                    not directory.startswith(".")
                    or directory in {".agents", ".github"}
                )
                and not directory.startswith(".venv-")
                and not directory.startswith("venv-")
                and not (
                    rel_root.as_posix() == "memory"
                    and directory == "cache"
                )
                and not (
                    rel_root.as_posix() == "memory"
                    and directory == "benchmarks"
                )
            )
            for file_name in sorted(file_names):
                file_path = current_path / file_name
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                rel_path = file_path.relative_to(self.project_root).as_posix()
                if (
                    Path(rel_path).parts[0] == "memory"
                    and Path(rel_path).suffix.lower() in {".json", ".pickle", ".pkl"}
                ):
                    continue
                try:
                    file_stat = file_path.stat()
                    hashes[rel_path] = self._hash_file(file_path)
                except OSError as err:
                    logger.warning("Could not hash repository file %s: %s", file_path, err)
                    continue
                file_stats[rel_path] = self._stat_signature(file_stat)

        self.current_snapshot = dict(sorted(hashes.items()))
        self.current_file_stats = dict(sorted(file_stats.items()))
        return self.current_snapshot

    def matches_current_stat(self, relative_path: str, file_path: Path) -> bool:
        """Checks whether a file still has the metadata observed during snapshotting."""
        expected = self.current_file_stats.get(relative_path.replace("\\", "/"))
        if expected is None:
            return False
        try:
            return expected == self._stat_signature(file_path.stat())
        except OSError:
            return False

    @staticmethod
    def _stat_signature(
        file_stat: os.stat_result,
    ) -> tuple[int, int, int, int]:
        return (
            file_stat.st_size,
            file_stat.st_mtime_ns,
            file_stat.st_ctime_ns,
            getattr(file_stat, "st_ino", 0),
        )

    @staticmethod
    def _hash_file(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def load(self) -> Dict[str, str]:
        """Loads a valid persisted snapshot, or returns an empty snapshot."""
        try:
            data = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Repository snapshot root must be a JSON object.")
            if data.get("version") != self.VERSION or not isinstance(data.get("files"), dict):
                logger.warning("Ignoring incompatible repository snapshot at %s", self.snapshot_path)
                return {}
            return {
                str(path): str(content_hash)
                for path, content_hash in sorted(data["files"].items())
                if isinstance(path, str) and isinstance(content_hash, str)
            }
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError) as err:
            logger.warning("Could not load repository snapshot %s: %s", self.snapshot_path, err)
            return {}

    def detect(self, previous_snapshot: Optional[Mapping[str, str]] = None) -> ChangeSet:
        """Classifies changed, added, deleted, renamed, test, and documentation files."""
        previous = dict(previous_snapshot) if previous_snapshot is not None else self.load()
        current = self.snapshot()
        modified = sorted(
            path for path in current.keys() & previous.keys()
            if current[path] != previous[path]
        )
        new = set(current) - set(previous)
        deleted = set(previous) - set(current)
        renamed: Dict[str, str] = {}

        old_by_hash: Dict[str, list[str]] = {}
        new_by_hash: Dict[str, list[str]] = {}
        for old_path in sorted(deleted):
            old_by_hash.setdefault(previous[old_path], []).append(old_path)
        for new_path in sorted(new):
            new_by_hash.setdefault(current[new_path], []).append(new_path)
        for content_hash in sorted(old_by_hash.keys() & new_by_hash.keys()):
            for old_path, new_path in zip(old_by_hash[content_hash], new_by_hash[content_hash]):
                renamed[old_path] = new_path
                deleted.remove(old_path)
                new.remove(new_path)

        changed_paths = set(modified) | set(new) | set(deleted)
        for old_path, new_path in renamed.items():
            changed_paths.update((old_path, new_path))

        changed_tests = sorted(path for path in changed_paths if self._is_test_file(path))
        changed_docs = sorted(path for path in changed_paths if self._is_documentation_file(path))
        return ChangeSet(
            modified_files=modified,
            deleted_files=sorted(deleted),
            renamed_files=dict(sorted(renamed.items())),
            new_files=sorted(new),
            changed_tests=changed_tests,
            changed_documentation=changed_docs,
            current_snapshot=current,
        )

    def save(self, snapshot: Optional[Mapping[str, str]] = None) -> None:
        """Persists the supplied snapshot (or the current repository snapshot) atomically."""
        files = dict(snapshot) if snapshot is not None else self.snapshot()
        if self.load() == dict(sorted(files.items())):
            return
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.snapshot_path.parent, delete=False
        ) as temp_file:
            json.dump(
                {"version": self.VERSION, "files": dict(sorted(files.items()))},
                temp_file,
                indent=2,
                sort_keys=True,
            )
            temp_path = Path(temp_file.name)
        temp_path.replace(self.snapshot_path)

    def detect_changes(self, previous_snapshot: Optional[Mapping[str, str]] = None) -> ChangeSet:
        """Compatibility-friendly alias for :meth:`detect`."""
        return self.detect(previous_snapshot)

    @staticmethod
    def _is_test_file(path: str) -> bool:
        name = Path(path).name.lower()
        return (
            (name.startswith("test_") and name.endswith(".py"))
            or name.endswith("_test.py")
            or ".test." in name
            or ".spec." in name
            or ("/__tests__/" in f"/{path.lower()}/")
        )

    @classmethod
    def _is_documentation_file(cls, path: str) -> bool:
        normalized = path.lower()
        name = Path(normalized).name
        return (
            Path(normalized).suffix in cls.DOCUMENTATION_SUFFIXES
            and (
                name == "readme.md"
                or "report" in name
                or "architecture" in name
                or "api" in name
                or normalized.startswith(("docs/", "documentation/"))
            )
        )


ChangeDetector = RepositoryChangeDetector
