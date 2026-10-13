"""Local dependency analysis built on AutoDev's existing scanner and analyzers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.dependency_intelligence.dependency_analyzer import DependencyAnalyzer
from core.dependency_intelligence.dependency_graph import DependencyGraph
from core.dependency_intelligence.dependency_scanner import DependencyScanner
from core.symbol_graph import SymbolGraph


class DependencyIntelligence:
    """Summarizes declared packages, imports, dependency risks, and opportunities."""

    MANIFEST_NAMES = {
        "requirements.txt", "requirements-dev.txt", "requirements.in",
        "pyproject.toml", "setup.py", "package.json", "pom.xml",
        "build.gradle", "build.gradle.kts", "Cargo.toml", "go.mod", "composer.json",
    }

    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        scanner: DependencyScanner | None = None,
        analyzer: DependencyAnalyzer | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.scanner = scanner or DependencyScanner()
        self.analyzer = analyzer or DependencyAnalyzer(self.scanner)

    def analyze(self, symbol_graph: SymbolGraph | None = None) -> dict[str, Any]:
        manifest_paths = self._manifest_paths()
        nodes = []
        for path in manifest_paths:
            nodes.extend(self.scanner.scan_manifest(str(path)))
        sources = self._source_files(symbol_graph)
        analysis = self.analyzer.analyze_dependencies(nodes, sources)
        graph = DependencyGraph()
        for node in sorted(nodes, key=lambda item: (item.name.casefold(), item.current_version, item.scope)):
            graph.add_dependency(node)
        imports = _imports(symbol_graph)
        duplicate_conflicts = []
        for package, versions in sorted(_declared_versions(nodes).items()):
            unique_versions = sorted(set(versions))
            if len(unique_versions) > 1:
                duplicate_conflicts.append({
                    "package": package,
                    "declared_versions": unique_versions,
                    "reason": "Multiple declarations specify different versions.",
                })
        deprecated = list(analysis["deprecated"])
        outdated = list(analysis["outdated"])
        unused = list(analysis["unused_packages"])
        risk_score = min(100, len(deprecated) * 25 + len(outdated) * 8 + len(unused) * 3 + len(duplicate_conflicts) * 12)
        return {
            "manifest_paths": [
                path.relative_to(self.project_root).as_posix()
                for path in manifest_paths
            ],
            "dependencies": [
                node.to_dict()
                for node in sorted(nodes, key=lambda item: (item.ecosystem.value, item.name.casefold(), item.current_version, item.scope))
            ],
            "import_graph": imports,
            "dependency_graph": graph.to_dict(),
            "summary": dict(analysis["summary"]),
            "duplicate_conflicts": duplicate_conflicts,
            "deprecated": deprecated,
            "outdated": outdated,
            "unused_packages": unused,
            "upgrade_opportunities": list(analysis["recommendations"]),
            "risk": {
                "score": risk_score,
                "level": "high" if risk_score >= 50 else "medium" if risk_score >= 20 else "low",
                "factors": {
                    "deprecated": len(deprecated),
                    "outdated": len(outdated),
                    "unused": len(unused),
                    "version_conflicts": len(duplicate_conflicts),
                },
            },
        }

    def _manifest_paths(self) -> list[Path]:
        ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
        return sorted(
            (
                path for path in self.project_root.rglob("*")
                if path.is_file()
                and path.name in self.MANIFEST_NAMES
                and not any(part in ignored for part in path.relative_to(self.project_root).parts)
            ),
            key=lambda item: item.relative_to(self.project_root).as_posix(),
        )

    def _source_files(self, graph: SymbolGraph | None) -> dict[str, str]:
        files = sorted(graph.files) if graph is not None else []
        if not files:
            ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
            files = [
                path.relative_to(self.project_root).as_posix()
                for path in self.project_root.rglob("*.py")
                if not any(part in ignored for part in path.relative_to(self.project_root).parts)
            ]
        content = {}
        for relative in files:
            path = self.project_root / relative
            try:
                if path.is_file() and path.stat().st_size <= 1_000_000:
                    content[relative] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
        return content


def _imports(graph: SymbolGraph | None) -> dict[str, list[str]]:
    if graph is None:
        return {}
    return {
        source: sorted(targets)
        for source, targets in sorted(graph.file_dependency_graph.items())
    }


def _declared_versions(nodes: list[Any]) -> dict[str, list[str]]:
    versions: dict[str, list[str]] = {}
    for node in nodes:
        versions.setdefault(node.name.casefold(), []).append(str(node.current_version))
    return versions
