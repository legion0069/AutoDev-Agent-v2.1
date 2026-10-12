"""
context_builder.py - Context Builder for AutoDev

Responsible for aggregating project metadata, active development state,
directory structure, and existing codebase files into a unified context
dictionary for the CoderAgent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.change_detector import RepositoryChangeDetector

logger = logging.getLogger("AutoDev.ContextBuilder")

# Directories to ignore during scanning
DEFAULT_IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "target",
    "dist",
    "build",
    ".pytest_cache",
    ".idea",
    ".vscode",
}

# Common binary file extensions to skip
BINARY_EXTENSIONS: Set[str] = {
    ".pyc", ".pyd", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".sqlite", ".sqlite3", ".db", ".wasm",
}


def is_text_file(file_path: Path, block_size: int = 1024) -> bool:
    """
    Determines whether a file is text-based by checking extension and byte content.

    Args:
        file_path: Path to the target file.
        block_size: Number of initial bytes to inspect for null characters.

    Returns:
        True if the file is text-based, False if binary or unreadable.
    """
    if file_path.suffix.lower() in BINARY_EXTENSIONS:
        return False

    try:
        with open(file_path, "rb") as f:
            chunk = f.read(block_size)
            # Binary files typically contain null bytes
            if b"\x00" in chunk:
                return False
        return True
    except (OSError, PermissionError):
        return False


class ContextBuilder:
    """
    Collects and synthesizes project plan data, state tracking, and workspace
    files into a structured context dictionary.
    """

    def __init__(
        self,
        plan_path: str | Path = "memory/project_plan.json",
        state_path: str | Path = "memory/state.json",
        project_root: Optional[str | Path] = None,
        ignored_dirs: Optional[Set[str]] = None,
        max_file_size_bytes: int = 1_000_000,
        cache_dir: Optional[str | Path] = None,
        change_detector: Optional[RepositoryChangeDetector] = None,
    ) -> None:
        """
        Initializes the ContextBuilder.

        Args:
            plan_path: Path to memory/project_plan.json.
            state_path: Path to memory/state.json.
            project_root: Root directory of the target project workspace.
            ignored_dirs: Set of directory names to ignore during scanning.
            max_file_size_bytes: Maximum size of text file to load into memory (default: 1MB).
        """
        self.plan_path = Path(plan_path)
        self.state_path = Path(state_path)
        self.project_root = Path(project_root) if project_root else None
        self.ignored_dirs = ignored_dirs if ignored_dirs is not None else DEFAULT_IGNORED_DIRS
        self.max_file_size_bytes = max_file_size_bytes
        self.cache_dir = Path(cache_dir).resolve() if cache_dir is not None else None
        self.change_detector = change_detector
        self._loaded_cache_path: Optional[Path] = None
        self._loaded_cache_mtime_ns: Optional[int] = None
        self._loaded_file_cache: Dict[str, Dict[str, str]] = {}

    def load_project_plan(self) -> Dict[str, Any]:
        """
        Loads and returns the project plan from memory/project_plan.json.
        """
        if not self.plan_path.is_file():
            raise FileNotFoundError(f"Project plan file not found at '{self.plan_path}'.")

        with open(self.plan_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_state(self) -> Dict[str, Any]:
        """
        Loads and returns the execution state from memory/state.json.
        """
        if not self.state_path.is_file():
            return {
                "current_day": 0,
                "completed_phases": [],
                "status": "initialized",
            }

        with open(self.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def scan_project_workspace(
        self,
        target_dir: Optional[Path] = None,
    ) -> tuple[List[str], Dict[str, str]]:
        """
        Scans the project directory tree and loads all text-based files.

        Args:
            target_dir: Optional override for the target workspace root.

        Returns:
            A tuple of (directory_tree_relative_paths, project_files_dict).
        """
        root = target_dir or self.project_root
        directory_tree: List[str] = []
        project_files: Dict[str, str] = {}

        if root is None or not root.exists() or not root.is_dir():
            return directory_tree, project_files

        root = root.resolve()
        cache_file = self._get_cache_file(root)
        cached_files = self._load_file_cache(cache_file)
        next_file_cache: Dict[str, Dict[str, str]] = {}

        for current_root, dirs, files in os.walk(root):
            # Prune ignored directories in-place
            rel_current = Path(current_root).relative_to(root).as_posix()
            dirs[:] = sorted(
                directory
                for directory in dirs
                if directory not in self.ignored_dirs
                and not directory.startswith((".venv-", "venv-"))
                and not (
                    rel_current == "memory"
                    and directory in {"cache", "benchmarks"}
                )
            )

            rel_root = Path(current_root).relative_to(root)

            for directory in sorted(dirs):
                rel_dir_path = (rel_root / directory).as_posix()
                directory_tree.append(f"{rel_dir_path}/")

            for file_name in sorted(files):
                file_path = Path(current_root) / file_name
                rel_file_path = (rel_root / file_name).as_posix()

                directory_tree.append(rel_file_path)

                try:
                    if file_path.stat().st_size > self.max_file_size_bytes:
                        continue
                    detected_hash = (
                        self.change_detector.current_snapshot.get(rel_file_path)
                        if self.change_detector is not None
                        else None
                    )
                    cached_entry = cached_files.get(rel_file_path)
                    if (
                        cached_entry
                        and cached_entry.get("hash") == detected_hash
                        and self.change_detector is not None
                        and self.change_detector.matches_current_stat(
                            rel_file_path,
                            file_path,
                        )
                    ):
                        content = cached_entry["content"]
                        project_files[rel_file_path] = content
                        next_file_cache[rel_file_path] = cached_entry
                        continue

                    if not is_text_file(file_path):
                        continue
                    raw_content = file_path.read_bytes()
                    actual_hash = hashlib.sha256(raw_content).hexdigest()
                    content_hash = detected_hash if detected_hash == actual_hash else actual_hash
                    if cached_entry and cached_entry.get("hash") == content_hash:
                        content = cached_entry["content"]
                    else:
                        content = raw_content.decode("utf-8", errors="replace")
                    project_files[rel_file_path] = content
                    next_file_cache[rel_file_path] = {
                        "hash": content_hash,
                        "content": content,
                    }
                except OSError as err:
                    logger.warning("Could not read workspace file %s: %s", file_path, err)
                    continue

        if next_file_cache != cached_files:
            self._save_file_cache(cache_file, next_file_cache)

        return directory_tree, project_files

    def _get_cache_file(self, root: Path) -> Path:
        cache_dir = self.cache_dir or root / "memory" / "cache" / "context"
        return cache_dir / "context_files.json"

    def _load_file_cache(self, cache_file: Path) -> Dict[str, Dict[str, str]]:
        try:
            stat = cache_file.stat()
            if (
                self._loaded_cache_path == cache_file
                and self._loaded_cache_mtime_ns == stat.st_mtime_ns
            ):
                return self._loaded_file_cache
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Context cache root must be a JSON object.")
            entries = data.get("files", {})
            if data.get("version") != 1 or not isinstance(entries, dict):
                raise ValueError("Unsupported or malformed context cache.")
            cache = {
                path: value
                for path, value in entries.items()
                if isinstance(path, str)
                and isinstance(value, dict)
                and isinstance(value.get("hash"), str)
                and isinstance(value.get("content"), str)
            }
            self._loaded_cache_path = cache_file
            self._loaded_cache_mtime_ns = stat.st_mtime_ns
            self._loaded_file_cache = cache
            return cache
        except FileNotFoundError:
            self._loaded_cache_path = cache_file
            self._loaded_cache_mtime_ns = None
            self._loaded_file_cache = {}
            return {}
        except (OSError, ValueError, TypeError) as err:
            logger.warning("Ignoring invalid context cache %s: %s", cache_file, err)
            self._loaded_cache_path = cache_file
            self._loaded_cache_mtime_ns = None
            self._loaded_file_cache = {}
            return {}

    def _save_file_cache(
        self,
        cache_file: Path,
        files: Dict[str, Dict[str, str]],
    ) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=cache_file.parent, delete=False
        ) as temp_file:
            json.dump(
                {"version": 1, "files": dict(sorted(files.items()))},
                temp_file,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            temp_path = Path(temp_file.name)
        temp_path.replace(cache_file)
        stat = cache_file.stat()
        self._loaded_cache_path = cache_file
        self._loaded_cache_mtime_ns = stat.st_mtime_ns
        self._loaded_file_cache = files

    def build(self, project_root: Optional[str | Path] = None) -> Dict[str, Any]:
        """
        Builds and returns the complete context dictionary.

        Args:
            project_root: Optional directory override for the project codebase.

        Returns:
            Structured dictionary containing all project metadata, phases,
            workspace directory tree, and file contents.
        """
        target_root = Path(project_root) if project_root else self.project_root

        plan = self.load_project_plan()
        state = self.load_state()

        project_name = plan.get("project_name", "")
        description = plan.get("project_description", "")
        technology_stack = plan.get("technology_stack", "")
        phases = plan.get("phases", [])

        # Determine current active day
        raw_current_day = state.get("current_day", 0)
        # If current_day is 0 (unstarted), default active phase to Day 1
        current_day = raw_current_day if raw_current_day > 0 else 1

        # Extract current phase object
        current_phase: Dict[str, Any] = {}
        for phase in phases:
            if phase.get("day") == current_day:
                current_phase = phase
                break

        completed_phases: List[Any] = state.get("completed_phases", [])

        # Scan directory tree and source files
        directory_tree, project_files = self.scan_project_workspace(target_dir=target_root)

        context: Dict[str, Any] = {
            "project_name": project_name,
            "description": description,
            "technology_stack": technology_stack,
            "current_day": current_day,
            "current_phase": current_phase,
            "completed_phases": completed_phases,
            "directory_tree": directory_tree,
            "project_files": project_files,
        }

        return context

    def build_context(
        self,
        current_day: Optional[int] = None,
        project_root: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """Compatibility wrapper for callers using the older build_context API."""
        context = self.build(project_root=project_root)
        if current_day is not None:
            plan = self.load_project_plan()
            context["current_day"] = current_day
            context["current_phase"] = next(
                (
                    phase
                    for phase in plan.get("phases", [])
                    if phase.get("day") == current_day
                ),
                {},
            )
        return context


def build_context(
    project_root: Optional[str | Path] = None,
    plan_path: str | Path = "memory/project_plan.json",
    state_path: str | Path = "memory/state.json",
) -> Dict[str, Any]:
    """
    Convenience function to build and return the complete project context.

    Args:
        project_root: Optional project workspace directory.
        plan_path: Path to memory/project_plan.json.
        state_path: Path to memory/state.json.

    Returns:
        Structured context dictionary.
    """
    builder = ContextBuilder(
        plan_path=plan_path,
        state_path=state_path,
        project_root=project_root,
    )
    return builder.build()


if __name__ == "__main__":
    # Self-test / demonstration
    ctx = build_context(project_root=Path.cwd())
    print("Built Context Keys:", list(ctx.keys()))
    print(f"Project Name      : {ctx['project_name']}")
    print(f"Current Day       : {ctx['current_day']}")
    print(f"Current Phase     : {ctx['current_phase'].get('phase_name', 'None')}")
    print(f"Total Files Scanned: {len(ctx['project_files'])}")
    print(f"Directory Entries : {len(ctx['directory_tree'])}")
