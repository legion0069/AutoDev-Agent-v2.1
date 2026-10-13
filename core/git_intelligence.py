"""Read-only local Git history, ownership, and hotspot analysis."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


class GitIntelligence:
    """Collects bounded local history without network access or repository mutation."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def analyze(self, *, limit: int = 100, file_limit: int = 100) -> dict[str, Any]:
        if limit < 0 or file_limit < 0:
            raise ValueError("limit values must not be negative.")
        if not self._is_repository():
            return {
                "available": False,
                "branch": None,
                "commits": [],
                "branches": [],
                "recent_changes": [],
                "failure_areas": [],
                "ownership": [],
                "hotspots": [],
            }
        branch = self._git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() or None
        commits = self._commits(limit)
        branches = self._branches()
        recent_changes = self._recent_changes(limit=min(limit, 100), file_limit=file_limit)
        failures = self._failure_areas(commits)
        ownership = self._ownership(recent_changes[:file_limit])
        counts = Counter(change["path"] for change in recent_changes)
        return {
            "available": True,
            "branch": branch,
            "head": self._git(["rev-parse", "HEAD"]).stdout.strip() or None,
            "commits": commits,
            "branches": branches,
            "recent_changes": recent_changes,
            "failure_areas": failures,
            "ownership": ownership,
            "hotspots": [
                {"path": path, "change_count": count}
                for path, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
            ],
        }

    def _is_repository(self) -> bool:
        result = self._git(["rev-parse", "--is-inside-work-tree"], check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _git(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_root), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Unable to inspect local Git repository: {exc}") from exc
        if check and result.returncode:
            raise RuntimeError(
                f"Git read command failed ({result.returncode}): git {' '.join(args)}: {result.stderr.strip()}"
            )
        return result

    def _commits(self, limit: int) -> list[dict[str, Any]]:
        if limit == 0:
            return []
        output = self._git([
            "log", f"-n{limit}", "--date=iso-strict",
            "--format=%H%x09%an%x09%ad%x09%s",
        ]).stdout
        commits = []
        for line in output.splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "timestamp": parts[2],
                    "subject": parts[3],
                })
        return commits

    def _branches(self) -> list[dict[str, Any]]:
        output = self._git([
            "for-each-ref",
            "--format=%(refname:short)%09%(objectname)%09%(committerdate:iso-strict)",
            "refs/heads",
        ]).stdout
        return [
            {"name": parts[0], "head": parts[1], "last_commit": parts[2]}
            for line in output.splitlines()
            if len(parts := line.split("\t", 2)) == 3
        ]

    def _recent_changes(self, *, limit: int, file_limit: int) -> list[dict[str, Any]]:
        if limit == 0 or file_limit == 0:
            return []
        output = self._git([
            "log", f"-n{limit}", "--format=commit:%H",
            "--name-only", "--diff-filter=ACMR",
        ]).stdout
        current = ""
        changes = []
        for line in output.splitlines():
            if line.startswith("commit:"):
                current = line.partition(":")[2]
            elif line.strip():
                path = line.strip().replace("\\", "/")
                changes.append({"commit": current, "path": path})
                if len(changes) >= file_limit:
                    break
        return changes

    @staticmethod
    def _failure_areas(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts = Counter()
        for commit in commits:
            subject = str(commit.get("subject", ""))
            if re.search(r"\b(fail(?:ed|ure)?|bug|fix(?:es|ed)?|regression|crash|error)\b", subject, re.I):
                for word in re.findall(r"[a-z0-9_.-]+", subject.casefold()):
                    if len(word) > 2 and word not in {"the", "and", "for", "with"}:
                        counts[word] += 1
        return [
            {"area": word, "mentions": count}
            for word, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ]

    def _ownership(self, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts = Counter(str(change["path"]) for change in changes)
        ownership = []
        for path in sorted(counts):
            author = self._git([
                "log", "-1", "--format=%an", "--follow", "--", path,
            ], check=False).stdout.strip()
            if author:
                ownership.append({
                    "path": path,
                    "author": author,
                    "recent_change_count": counts[path],
                })
        return ownership
