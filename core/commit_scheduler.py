"""Meaningful-change detection and V5.2 commit scheduling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.git_agent import GitAgent


class CommitScheduler:
    """Creates a commit only when meaningful source, test, docs, or config changed."""

    ALLOWED_SUFFIXES = {
        ".c",
        ".cfg",
        ".cpp",
        ".cs",
        ".css",
        ".go",
        ".h",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
    EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", "memory", "logs"}

    def __init__(self, git_agent: GitAgent) -> None:
        self.git_agent = git_agent

    def changed_files(self) -> list[str]:
        status = self.git_agent.get_status()
        candidates = sorted(
            set(status.modified_files + status.staged_files + status.untracked_files)
        )
        return [
            file_path
            for file_path in candidates
            if self._is_commit_candidate(file_path)
            and self._has_meaningful_content(file_path)
        ]

    def create_commit(self, day: int, milestone_title: str) -> Any | None:
        files = self.changed_files()
        if not files:
            return None
        title = " ".join(milestone_title.split())
        if not title:
            raise ValueError("A milestone title is required to create a commit.")
        result = self.git_agent.commit(
            message=f"Day {day} - {title}",
            files_to_stage=files,
        )
        if not result.success or not result.commit_hash:
            raise RuntimeError(
                result.error or result.message or "Could not create milestone commit."
            )
        return result

    def _is_commit_candidate(self, file_path: str) -> bool:
        path = Path(file_path)
        return (
            (
                path.suffix.lower() in self.ALLOWED_SUFFIXES
                or path.name in {".gitignore", "Dockerfile", "Makefile"}
            )
            and not any(part in self.EXCLUDED_PARTS for part in path.parts)
            and not path.name.endswith((".bak", ".tmp"))
        )

    def _has_meaningful_content(self, file_path: str) -> bool:
        path = self.git_agent.project_root / file_path
        if path.is_file():
            staged = self.git_agent._run_git_command(
                ["diff", "--cached", "--ignore-all-space", "--quiet", "--", file_path],
                check=False,
            )
            unstaged = self.git_agent._run_git_command(
                ["diff", "--ignore-all-space", "--quiet", "--", file_path],
                check=False,
            )
            if staged.returncode not in {0, 1} or unstaged.returncode not in {0, 1}:
                raise RuntimeError(
                    f"Cannot inspect whitespace-only changes in {file_path}."
                )
            if staged.returncode == 1 or unstaged.returncode == 1:
                return True
            if self.git_agent._run_git_command(
                ["ls-files", "--error-unmatch", "--", file_path],
                check=False,
            ).returncode:
                try:
                    return bool(path.read_bytes().strip())
                except OSError as exc:
                    raise RuntimeError(
                        f"Cannot inspect changed file {file_path}: {exc}"
                    ) from exc
            return False
        for args in (
            ["diff", "--ignore-all-space", "--", file_path],
            ["diff", "--cached", "--ignore-all-space", "--", file_path],
        ):
            result = self.git_agent._run_git_command(args, check=False)
            if result.returncode:
                raise RuntimeError(
                    f"Cannot inspect changed file {file_path}: {result.stderr.strip()}"
                )
            if result.stdout.strip():
                return True
        return False

    @staticmethod
    def meets_target(commit_count: int, target: int) -> bool:
        return commit_count >= target
