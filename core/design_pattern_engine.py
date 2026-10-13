"""AST-backed design-pattern recognition and anti-pattern recommendations."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any


class DesignPatternEngine:
    """Finds recognizable implementation patterns and actionable code smells."""

    def analyze(self, project_root: str | Path) -> dict[str, Any]:
        root = Path(project_root).resolve()
        patterns: list[dict[str, Any]] = []
        anti_patterns: list[dict[str, Any]] = []
        analysis_errors: list[dict[str, str]] = []
        for current, directories, filenames in os.walk(root):
            directories[:] = sorted(
                name for name in directories
                if name not in {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}
                and not name.startswith(".venv-")
            )
            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                path = Path(current) / filename
                relative = path.relative_to(root).as_posix()
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
                except (OSError, UnicodeError, SyntaxError) as exc:
                    line = getattr(exc, "lineno", None)
                    detail = f"SyntaxError at line {line}: {exc.msg}" if isinstance(exc, SyntaxError) else f"{type(exc).__name__}: {exc}"
                    analysis_errors.append({"file": relative, "error": detail})
                    continue
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.lower().startswith(("create_", "build_", "make_")):
                            patterns.append(self._pattern("factory", relative, node.name, node.lineno))
                        if len(node.body) > 40 or getattr(node, "end_lineno", node.lineno) - node.lineno > 50:
                            anti_patterns.append({
                                "kind": "long_function",
                                "location": f"{relative}:{node.lineno}",
                                "recommendation": "Extract cohesive steps into small private helpers.",
                            })
                    if isinstance(node, ast.ClassDef):
                        names = {member.name.lower() for member in node.body if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))}
                        lower_name = node.name.lower()
                        if "repository" in lower_name:
                            patterns.append(self._pattern("repository", relative, node.name, node.lineno))
                        if "adapter" in lower_name or "wrapper" in lower_name:
                            patterns.append(self._pattern("adapter", relative, node.name, node.lineno))
                        if names & {"subscribe", "unsubscribe", "notify", "publish"}:
                            patterns.append(self._pattern("observer", relative, node.name, node.lineno))
                        if names & {"get_instance", "instance"}:
                            patterns.append(self._pattern("singleton", relative, node.name, node.lineno))
                        if names & {"execute", "run", "apply", "handle"} and len(names) >= 2:
                            patterns.append(self._pattern("strategy_candidate", relative, node.name, node.lineno))
                        if len(names) > 12:
                            anti_patterns.append({
                                "kind": "god_class",
                                "location": f"{relative}:{node.lineno}",
                                "method_count": len(names),
                                "recommendation": "Split the class by responsibility and preserve its public facade.",
                            })
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler) and node.type is None:
                        anti_patterns.append({
                            "kind": "bare_except",
                            "location": f"{relative}:{node.lineno}",
                            "recommendation": "Catch explicit exceptions and preserve diagnostic context.",
                        })

        patterns = self._unique_sorted(patterns)
        anti_patterns = self._unique_sorted(anti_patterns)
        suggestions = sorted({
            f"Review {item['kind']} at {item['location']}."
            for item in anti_patterns
        })
        return {
            "patterns": patterns,
            "anti_patterns": anti_patterns,
            "recommendations": suggestions,
            "analysis_errors": sorted(analysis_errors, key=lambda item: (item["file"], item["error"])),
        }

    @staticmethod
    def _pattern(kind: str, path: str, name: str, line: int) -> dict[str, Any]:
        return {
            "kind": kind,
            "location": f"{path}:{line}",
            "symbol": name,
            "recommendation": (
                "Keep the pattern when it reduces coupling; avoid additional indirection without a measured need."
            ),
        }

    @staticmethod
    def _unique_sorted(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique = {
            (item["kind"], item["location"], item.get("symbol", "")): item
            for item in items
        }
        return [unique[key] for key in sorted(unique)]
