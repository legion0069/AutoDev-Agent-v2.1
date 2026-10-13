"""Architecture inspection and deterministic evolution recommendations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.repository_analyzer import RepositoryAnalyzer
from core.symbol_graph import SymbolGraph


class ArchitectureEvolutionEngine:
    """Reuses repository intelligence to identify architectural risk and options."""

    def __init__(self, analyzer: RepositoryAnalyzer | None = None) -> None:
        self.analyzer = analyzer

    def analyze(
        self,
        project_root: str | Path,
        symbol_graph: SymbolGraph | None = None,
        code_quality: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        root = Path(project_root).resolve()
        overview = (self.analyzer or RepositoryAnalyzer(project_root=root)).analyze(
            project_root=root,
            symbol_graph=symbol_graph,
        )
        hotspots = sorted(
            (item.to_dict() for item in overview.hotspots),
            key=lambda item: (-float(item.get("score", 0)), str(item.get("target", ""))),
        )
        cycles = sorted(
            (item.to_dict() for item in overview.circular_dependencies),
            key=lambda item: tuple(item.get("cycle", [])),
        )
        recommendations: list[dict[str, Any]] = []
        for cycle in cycles:
            recommendations.append({
                "title": "Break circular module dependencies",
                "priority": "high",
                "evidence": cycle.get("cycle", []),
                "action": "Move shared contracts to a lower-level module.",
            })
        for hotspot in hotspots:
            if hotspot.get("category") in {"largest_module", "god_object", "high_fan_out"}:
                recommendations.append({
                    "title": f"Reduce architectural hotspot: {hotspot['target']}",
                    "priority": "high" if hotspot.get("category") == "god_object" else "medium",
                    "evidence": [hotspot],
                    "action": "Split cohesive responsibilities behind stable interfaces.",
                })
        quality = code_quality or {}
        for item in quality.get("recommendations", []):
            if "maintainability" in str(item).lower() or "complexity" in str(item).lower():
                recommendations.append({
                    "title": str(item),
                    "priority": "medium",
                    "evidence": [],
                    "action": "Simplify the identified implementation while preserving its public contract.",
                })
        recommendations = sorted(
            recommendations,
            key=lambda item: (
                0 if item["priority"] == "high" else 1,
                item["title"],
            ),
        )

        module_count = max(1, overview.total_modules)
        complexity_ratio = min(1.0, len(hotspots) / module_count)
        cycle_ratio = min(1.0, len(cycles) / module_count)
        maintainability = round(max(0.0, 100.0 - 60.0 * complexity_ratio - 80.0 * cycle_ratio), 2)
        architectures = sorted(
            (item.to_dict() for item in overview.detected_architectures),
            key=lambda item: (-float(item.get("confidence", 0)), str(item.get("pattern_name", ""))),
        )
        return {
            "project_name": overview.project_name,
            "module_count": overview.total_modules,
            "symbol_count": overview.total_symbols,
            "architectures": architectures,
            "hotspots": hotspots,
            "bottlenecks": [item for item in hotspots if item.get("category") in {"high_fan_out", "high_fan_in"}],
            "circular_dependencies": cycles,
            "dead_code_candidates": sorted(overview.dead_code_candidates),
            "recommendations": recommendations,
            "maintainability_estimate": maintainability,
            "alternatives": [
                {"name": "retain_current_boundaries", "maintainability_estimate": maintainability},
                {
                    "name": "reduce_coupling_and_split_hotspots",
                    "maintainability_estimate": round(min(100.0, maintainability + 10.0), 2),
                },
            ],
        }
