"""Verified remote commit publishing for the V5.2 execution engine."""

from __future__ import annotations

import time
from typing import Any

from agents.git_agent import GitAgent


class GitHubPushError(RuntimeError):
    def __init__(self, message: str, commit_hash: str) -> None:
        super().__init__(message)
        self.commit_hash = commit_hash


class GitHubExecution:
    def __init__(
        self, git_agent: GitAgent, retries: int = 3, retry_delay: float = 1.0
    ) -> None:
        self.git_agent = git_agent
        self.retries = max(1, retries)
        self.retry_delay = max(0.0, retry_delay)

    def push_and_verify(self, expected_hash: str) -> dict[str, Any]:
        branch = self.git_agent.get_current_branch()
        if not branch:
            raise RuntimeError("Cannot push without an active Git branch.")
        last_error = "Push did not succeed."
        current_hash = expected_hash
        for attempt in range(1, self.retries + 1):
            result = self.git_agent.push(branch=branch, set_upstream=attempt == 1)
            if result.success and self._remote_contains(branch, current_hash):
                return {
                    "success": True,
                    "verified": True,
                    "branch": branch,
                    "commit_hash": current_hash,
                    "attempts": attempt,
                }
            last_error = (
                result.message or result.stderr or "Remote verification failed."
            )
            conflict = any(
                token in f"{result.stderr} {result.message}".lower()
                for token in ("non-fast-forward", "fetch first", "rejected")
            )
            if conflict and attempt < self.retries:
                pull = self.git_agent._run_git_command(
                    ["pull", "--rebase", "origin", branch],
                    check=False,
                    timeout=120,
                )
                if pull.returncode:
                    self.git_agent._run_git_command(
                        ["rebase", "--abort"],
                        check=False,
                        timeout=30,
                    )
                    raise GitHubPushError(
                        f"Push conflict could not be rebased safely: {pull.stderr.strip() or pull.stdout.strip()}",
                        current_hash,
                    )
                current_hash = self.git_agent.get_latest_commit_hash() or current_hash
            if attempt < self.retries and self.retry_delay:
                time.sleep(self.retry_delay)
        raise GitHubPushError(
            f"Push could not be verified after {self.retries} attempts: {last_error}",
            current_hash,
        )

    def _remote_contains(self, branch: str, expected_hash: str) -> bool:
        result = self.git_agent._run_git_command(
            ["ls-remote", "origin", f"refs/heads/{branch}"],
            check=False,
            timeout=30,
        )
        if result.returncode:
            return False
        remote_hash = (
            result.stdout.strip().split(maxsplit=1)[0] if result.stdout.strip() else ""
        )
        if remote_hash == expected_hash:
            return True
        if not remote_hash:
            return False
        fetched = self.git_agent._run_git_command(
            ["fetch", "--quiet", "origin", branch],
            check=False,
            timeout=60,
        )
        if fetched.returncode:
            return False
        ancestry = self.git_agent._run_git_command(
            ["merge-base", "--is-ancestor", expected_hash, "FETCH_HEAD"],
            check=False,
        )
        return ancestry.returncode == 0
