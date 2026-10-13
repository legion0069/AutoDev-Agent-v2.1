"""Standard-library benchmarks for AutoDev V3.11 environment intelligence."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api_discovery import APIDiscoveryEngine
from core.dependency_intelligence import DependencyIntelligence
from core.environment_analyzer import EnvironmentAnalyzer
from core.environment_controller import EnvironmentController
from core.git_intelligence import GitIntelligence
from core.incremental_indexer import IncrementalIndexer
from core.repository_intelligence import RepositoryIntelligence
from core.tool_registry import ToolRegistry
from core.tool_selector import ToolSelector


def _measure(
    operation: Callable[[], object],
    iterations: int,
) -> dict[str, float | int]:
    durations = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        durations.append(time.perf_counter() - started)
    return {
        "iterations": iterations,
        "min_seconds": round(min(durations), 8),
        "median_seconds": round(statistics.median(durations), 8),
        "mean_seconds": round(statistics.mean(durations), 8),
        "max_seconds": round(max(durations), 8),
    }


def run_benchmarks(
    output_dir: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    iterations: int = 3,
) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be at least 1.")
    root = Path(project_root or ROOT).resolve()
    target = Path(output_dir or ROOT / "memory" / "benchmarks").resolve()
    target.mkdir(parents=True, exist_ok=True)

    indexer = IncrementalIndexer(project_root=root)
    graph = indexer.index_project()
    environment_analyzer = EnvironmentAnalyzer(root)
    repository_intelligence = RepositoryIntelligence(root, graph)
    dependency_intelligence = DependencyIntelligence(root)
    git_intelligence = GitIntelligence(root)
    api_discovery = APIDiscoveryEngine(root)
    registry = ToolRegistry(discover=True)
    selector = ToolSelector(registry)
    controller = EnvironmentController(root, tool_registry=registry)

    metrics = {
        "environment_scan_latency": _measure(environment_analyzer.analyze, iterations),
        "repository_scan_latency": _measure(
            lambda: repository_intelligence.analyze(graph),
            iterations,
        ),
        "dependency_analysis_latency": _measure(
            lambda: dependency_intelligence.analyze(graph),
            iterations,
        ),
        "git_analysis_latency": _measure(
            lambda: git_intelligence.analyze(limit=25, file_limit=40),
            iterations,
        ),
        "tool_selection_latency": _measure(
            lambda: selector.select("Run Python tests", capability="test"),
            iterations,
        ),
        "api_discovery_latency": _measure(api_discovery.discover, iterations),
        "environment_report_generation_latency": _measure(
            lambda: controller.analyze(
                symbol_graph=graph,
                task="Analyze repository and plan environment-aware engineering work",
            ),
            iterations,
        ),
    }
    results: dict[str, object] = {
        "version": "3.11",
        "iterations": iterations,
        "project_root": str(root),
        "metrics": dict(sorted(metrics.items())),
        "notes": (
            "Local read-only environment-intelligence benchmarks; timings vary by host "
            "and are not release performance claims."
        ),
    }
    history_path = target / "v311_benchmark_history.json"
    history = []
    if history_path.exists():
        loaded = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError(f"Benchmark history must contain a JSON list: {history_path}")
        history = loaded
    history.append(results)
    (target / "v311_benchmark_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    history_path.write_text(
        json.dumps(history, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        "version": "3.11",
        "benchmark_count": len(metrics),
        "metrics": {
            name: {
                key: values[key]
                for key in ("mean_seconds", "median_seconds", "min_seconds", "max_seconds")
            }
            for name, values in metrics.items()
        },
        "notes": results["notes"],
    }
    (target / "v311_performance_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


if __name__ == "__main__":
    print(json.dumps(run_benchmarks(), indent=2, sort_keys=True))
