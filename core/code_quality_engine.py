"""Deterministic static code-quality analysis using existing AutoDev analyzers."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from core.complexity_analyzer import ComplexityAnalyzer
from core.duplication_detector import DuplicationDetector
from core.symbol_graph import SymbolGraph


class CodeQualityEngine:
    """Summarizes complexity, coupling, cohesion, duplication, dead code, and boundaries."""

    IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}

    def __init__(self) -> None:
        self.complexity_analyzer = ComplexityAnalyzer()
        self.duplication_detector = DuplicationDetector()

    def analyze(
        self,
        project_root: str | Path,
        symbol_graph: SymbolGraph | None = None,
    ) -> dict[str, Any]:
        root = Path(project_root).resolve()
        contents: dict[str, str] = {}
        analysis_errors: list[dict[str, str]] = []
        for current, directories, filenames in os.walk(root):
            directories[:] = sorted(
                name for name in directories
                if name not in self.IGNORED_DIRS and not name.startswith(".venv-")
            )
            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                path = Path(current) / filename
                relative = path.relative_to(root).as_posix()
                try:
                    contents[relative] = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    analysis_errors.append({
                        "file": relative,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    continue

        parsed: dict[str, ast.Module] = {}
        for path, source in sorted(contents.items()):
            try:
                parsed[path] = ast.parse(source, filename=path)
            except SyntaxError as exc:
                analysis_errors.append({
                    "file": path,
                    "error": f"SyntaxError at line {exc.lineno}: {exc.msg}",
                })
        file_metrics = {
            path: self.complexity_analyzer.analyze_source(source, path).to_dict()
            for path, source in sorted(contents.items())
        }
        duplication_blocks, duplication_ratio = self.duplication_detector.scan_files(contents)
        dependencies: dict[str, set[str]] = {path: set() for path in contents}
        if symbol_graph is not None:
            for source, targets in symbol_graph.file_dependency_graph.items():
                if source in dependencies:
                    dependencies[source].update(target for target in targets if target in contents)
        else:
            for path, tree in parsed.items():
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            dependencies[path].add(alias.name.replace(".", "/") + ".py")
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        dependencies[path].add(node.module.replace(".", "/") + ".py")

        coupling_values = [len(targets) for targets in dependencies.values()]
        coupling = sum(coupling_values) / len(coupling_values) if coupling_values else 0.0
        cohesion_values: list[float] = []
        references: dict[str, int] = {}
        for path, tree in parsed.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    references[node.id] = references.get(node.id, 0) + 1
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                methods = [member for member in node.body if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))]
                state_sets = [self._self_attributes(method) for method in methods]
                if len(state_sets) < 2:
                    continue
                possible = len(state_sets) * (len(state_sets) - 1) / 2
                shared = sum(
                    bool(state_sets[left] & state_sets[right])
                    for left in range(len(state_sets))
                    for right in range(left + 1, len(state_sets))
                )
                cohesion_values.append(shared / possible if possible else 1.0)

        dead_code: list[str] = []
        high_complexity: list[dict[str, Any]] = []
        for path, source in contents.items():
            if path.startswith("tests/"):
                continue
            tree = parsed.get(path)
            if tree is None:
                continue
            metrics = file_metrics[path]
            if metrics["cyclomatic_complexity"] >= 20 or metrics["maintainability_index"] < 50:
                high_complexity.append({
                    "file": path,
                    "cyclomatic_complexity": metrics["cyclomatic_complexity"],
                    "maintainability_index": metrics["maintainability_index"],
                })
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (
                        node.name not in {"main", "__main__"}
                        and references.get(node.name, 0) == 0
                    ):
                        dead_code.append(f"{path}:{node.name}")

        violations = self._architecture_violations(dependencies)
        average_mi = (
            sum(float(item["maintainability_index"]) for item in file_metrics.values())
            / len(file_metrics)
            if file_metrics else 100.0
        )
        avg_cohesion = sum(cohesion_values) / len(cohesion_values) if cohesion_values else 1.0
        recommendations = []
        if high_complexity:
            recommendations.append("Simplify high-complexity modules and functions.")
        if coupling > 5:
            recommendations.append("Reduce module coupling by separating shared interfaces.")
        if avg_cohesion < 0.5:
            recommendations.append("Improve class cohesion by grouping related responsibilities.")
        if duplication_ratio > 5:
            recommendations.append("Consolidate repeated code behind shared helpers.")
        if dead_code:
            recommendations.append("Review possible dead-code candidates before removal.")
        if violations:
            recommendations.append("Correct imports that cross the declared architecture boundary.")
        return {
            "file_count": len(contents),
            "complexity": {
                "average_cyclomatic": round(
                    sum(item["cyclomatic_complexity"] for item in file_metrics.values()) / len(file_metrics),
                    2,
                ) if file_metrics else 0.0,
                "hotspots": sorted(high_complexity, key=lambda item: item["file"]),
            },
            "maintainability_index": round(average_mi, 2),
            "coupling": round(coupling, 2),
            "cohesion": round(avg_cohesion, 3),
            "duplication_ratio": duplication_ratio,
            "duplication_count": len(duplication_blocks),
            "dead_code_candidates": sorted(dead_code),
            "architecture_violations": sorted(violations),
            "complexity_hotspots": sorted(item["file"] for item in high_complexity),
            "recommendations": recommendations,
            "analysis_errors": sorted(analysis_errors, key=lambda item: (item["file"], item["error"])),
            "files": file_metrics,
        }

    @staticmethod
    def _self_attributes(method: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        return {
            node.attr
            for node in ast.walk(method)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        }

    @staticmethod
    def _architecture_violations(dependencies: dict[str, set[str]]) -> list[str]:
        violations = []
        for source, targets in dependencies.items():
            if source.startswith("core/") and source != "core/orchestrator.py":
                for target in targets:
                    if target.startswith("agents/"):
                        violations.append(f"{source} imports higher-level module {target}")
        return violations
