"""Section-oriented documentation updates for incremental AutoDev workflows."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Mapping, Optional

from core.execution_scheduler import ExecutionScheduler

logger = logging.getLogger("AutoDev.DocIncrementalBuilder")


class DocIncrementalBuilder:
    """Rewrites only named, managed documentation sections that actually changed."""

    SECTION_PATTERN = re.compile(
        r"(?P<start><!-- autodev:section:(?P<key>[0-9a-f]{16}):start -->\n)"
        r"(?P<body>.*?)"
        r"(?P<end><!-- autodev:section:(?P=key):end -->)",
        re.DOTALL,
    )

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self._document_cache: dict[
            Path,
            tuple[tuple[int, int, int, int], dict[str, str]],
        ] = {}

    def update_document(
        self,
        path: str | Path,
        sections: Mapping[str, str],
    ) -> bool:
        """Updates requested sections and preserves all text outside their markers."""
        if not sections:
            return False
        target = Path(path).resolve()
        try:
            initial_stat = target.stat()
        except FileNotFoundError:
            initial_stat = None
        if initial_stat is not None:
            signature = self._stat_signature(initial_stat)
            cached = self._document_cache.get(target)
            if cached is not None and cached[0] == signature and cached[1] == sections:
                return False
        section_signature = tuple(
            (name, content.rstrip())
            for name, content in sorted(sections.items())
        )
        original = target.read_text(encoding="utf-8") if target.exists() else ""
        matches: dict[str, re.Match[str]] = {}
        for match in self.SECTION_PATTERN.finditer(original):
            matches.setdefault(match.group("key"), match)
        replacements: list[tuple[int, int, str]] = []
        appended: list[str] = []
        for section_name, content in section_signature:
            key = hashlib.sha256(section_name.encode("utf-8")).hexdigest()[:16]
            start = f"<!-- autodev:section:{key}:start -->\n"
            end = f"<!-- autodev:section:{key}:end -->"
            replacement = f"{start}{content}\n{end}"
            match = matches.get(key)
            if match:
                if match.group(0) != replacement:
                    replacements.append((match.start(), match.end(), replacement))
            else:
                appended.append(replacement)

        changed = bool(replacements or appended)
        if changed:
            parts: list[str] = []
            last_position = 0
            for start, end, replacement in sorted(replacements):
                parts.extend((original[last_position:start], replacement))
                last_position = end
            parts.append(original[last_position:])
            updated = "".join(parts)
            if appended:
                separator = "" if not updated else ("\n" if updated.endswith("\n") else "\n\n")
                updated += separator + "\n\n".join(appended) + "\n"
            self._atomic_write(target, updated)
            logger.info("Updated managed documentation sections in %s", target)
        try:
            current_stat = target.stat()
        except OSError:
            self._document_cache.pop(target, None)
        else:
            self._document_cache[target] = (
                self._stat_signature(current_stat),
                dict(sections),
            )
        return changed

    @staticmethod
    def _stat_signature(file_stat: os.stat_result) -> tuple[int, int, int, int]:
        return (
            file_stat.st_size,
            file_stat.st_mtime_ns,
            file_stat.st_ctime_ns,
            getattr(file_stat, "st_ino", 0),
        )

    def update_documents(
        self,
        documents: Mapping[str | Path, Mapping[str, str]],
    ) -> Dict[str, bool]:
        """Updates independent documents concurrently and returns per-path change flags."""
        scheduler = ExecutionScheduler(max_workers=self.max_workers)
        path_map: dict[str, Path] = {}
        for path, sections in sorted(
            documents.items(),
            key=lambda item: str(item[0]),
        ):
            target = Path(path)
            task_id = str(target.resolve())
            if task_id in path_map:
                raise ValueError(f"Duplicate documentation target: {target}")
            path_map[task_id] = target
            scheduler.add_task(
                task_id,
                self.update_document,
                args=(target, sections),
            )
        results = scheduler.execute()
        return {
            str(path_map[task_id]): bool(results[task_id])
            for task_id in sorted(results)
        }

    def document_kind(self, path: str | Path) -> str:
        """Classifies README, engineering, architecture, and API documentation."""
        normalized = str(path).replace("\\", "/").lower()
        name = Path(normalized).name
        if name.startswith("readme"):
            return "readme"
        if "architecture" in name or "/architecture" in normalized:
            return "architecture"
        if "api" in name or "/api" in normalized:
            return "api"
        if "engineering" in name or "report" in name:
            return "engineering_report"
        return "documentation"

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent, delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        temp_path.replace(target)
