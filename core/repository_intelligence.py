"""Repository structure and health analysis reusing AutoDev's symbol graph."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from core.cache_manager import CacheManager
from core.change_detector import RepositoryChangeDetector
from core.incremental_indexer import IncrementalIndexer
from core.repository_analyzer import RepositoryAnalyzer
from core.symbol_graph import SymbolGraph


class RepositoryIntelligence:
    """Adds package ownership and build-graph facts to RepositoryAnalyzer output."""

    def __init__(self, project_root: str | Path = ".", symbol_graph: SymbolGraph | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.symbol_graph = symbol_graph

    def analyze(self, symbol_graph: SymbolGraph | None = None) -> dict[str, Any]:
        graph = symbol_graph or self.symbol_graph
        if graph is None:
            detector = RepositoryChangeDetector(self.project_root)
            indexer = IncrementalIndexer(
                project_root=self.project_root,
                change_detector=detector,
                cache_manager=CacheManager(self.project_root / "memory" / "cache"),
            )
            graph = indexer.index_project(changes=detector.detect())
        overview = RepositoryAnalyzer(
            project_root=self.project_root,
            symbol_graph=graph,
            output_path=self.project_root / "memory" / "cache" / "repository_intelligence.json",
        ).analyze(project_root=self.project_root, symbol_graph=graph)
        data = overview.to_dict()
        data.pop("timestamp", None)
        files = sorted(set(overview.module_summaries) | set(graph.files if graph else ()))
        packages = self._packages(files)
        ownership = self._ownership(files)
        dependencies = {
            path: sorted(targets)
            for path, targets in sorted((graph.file_dependency_graph if graph else {}).items())
        }
        build_graph = self._build_graph()
        cycles = data.get("circular_dependencies", [])
        dead_code_count = len(data.get("dead_code_candidates", []))
        module_count = int(data.get("total_modules", 0))
        health_score = max(0, min(100, 100 - len(cycles) * 8 - min(dead_code_count, 20) * 2))
        data.update({
            "packages": packages,
            "ownership": ownership,
            "dependency_graph": dependencies,
            "build_graph": build_graph,
            "repository_health": {
                "score": health_score,
                "grade": _grade(health_score),
                "module_count": module_count,
                "circular_dependency_count": len(cycles),
                "dead_code_candidate_count": dead_code_count,
                "status": "healthy" if not cycles and health_score >= 80 else "review",
            },
        })
        return data

    def _packages(self, files: list[str]) -> list[dict[str, Any]]:
        package_files: dict[str, list[str]] = {}
        for file_path in files:
            path = Path(file_path)
            if path.name == "__init__.py":
                package = path.parent.as_posix()
                package_files.setdefault(package, []).append(file_path)
        return [
            {"name": path.rsplit("/", 1)[-1], "path": path, "files": sorted(paths)}
            for path, paths in sorted(package_files.items())
        ]

    def _ownership(self, files: list[str]) -> list[dict[str, str]]:
        codeowners = next(
            (
                path for path in (
                    self.project_root / "CODEOWNERS",
                    self.project_root / ".github" / "CODEOWNERS",
                    self.project_root / "docs" / "CODEOWNERS",
                )
                if path.is_file()
            ),
            None,
        )
        if codeowners is None:
            return []
        rules = []
        for raw in codeowners.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.partition("#")[0].strip()
            parts = line.split()
            if len(parts) >= 2:
                rules.append((parts[0].lstrip("/"), parts[1]))
        result = []
        for file_path in files:
            owners = [
                owner for pattern, owner in rules
                if fnmatch.fnmatch(file_path, pattern)
                or fnmatch.fnmatch(Path(file_path).name, pattern)
            ]
            if owners:
                result.append({"path": file_path, "owners": " ".join(sorted(set(owners)))})
        return result

    def _build_graph(self) -> dict[str, list[str]]:
        manifests = {
            "requirements.txt": "python",
            "pyproject.toml": "python",
            "setup.py": "python",
            "package.json": "javascript",
            "pom.xml": "java",
            "build.gradle": "java",
            "Cargo.toml": "rust",
            "go.mod": "go",
            "Makefile": "native",
            "CMakeLists.txt": "native",
            "Dockerfile": "container",
        }
        existing = [name for name in manifests if (self.project_root / name).is_file()]
        return {
            name: sorted({
                "test" if name in {"requirements.txt", "pyproject.toml", "package.json", "pom.xml", "build.gradle"} else "build",
                manifests[name],
            })
            for name in sorted(existing)
        }


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
