"""Repeatable standard-library latency benchmarks for AutoDev v4.0."""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.architecture_evolution import ArchitectureEvolutionEngine
from core.evolution_controller import EvolutionController
from core.experiment_engine import EvolutionExperimentEngine
from core.incremental_indexer import IncrementalIndexer
from core.research_engine import ResearchEngine
from core.self_optimizer import SelfOptimizer
from core.software_knowledge_graph import SoftwareKnowledgeGraph


def _measure(operation: Callable[[], object], iterations: int) -> dict[str, float | int]:
    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - started)
    return {
        "iterations": iterations,
        "min_seconds": round(min(samples), 8),
        "median_seconds": round(statistics.median(samples), 8),
        "mean_seconds": round(statistics.fmean(samples), 8),
        "max_seconds": round(max(samples), 8),
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def run_benchmarks(
    output_dir: str | Path = "memory/benchmarks",
    iterations: int = 5,
) -> dict[str, object]:
    """Measures all v4 engines using a small, isolated, reproducible project."""
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")

    with tempfile.TemporaryDirectory(prefix="autodev-v40-benchmark-") as scratch:
        root = Path(scratch)
        source = root / "src" / "sample.py"
        source.parent.mkdir(parents=True)
        source.write_text(
            "class Sample:\n"
            "    def execute(self, value):\n"
            "        return value + 1\n",
            encoding="utf-8",
        )
        graph = IncrementalIndexer(project_root=root).index_project(parallel=False)
        research = ResearchEngine()
        problem = research.discover_problem({
            "problems": [{
                "title": "Reduce sample planning latency",
                "severity": "MEDIUM",
                "evidence": {"latency_seconds": 1.1},
            }]
        })
        if problem is None:
            raise RuntimeError("Benchmark setup did not discover its declared research problem.")
        research_plan = research.generate_research_plan(problem)
        optimizer = SelfOptimizer()

        def run_experiment() -> dict[str, object]:
            engine = EvolutionExperimentEngine()
            experiment = engine.create_experiment(
                "benchmark candidate implementations",
                lambda _: 10.0,
                {"optimized": lambda _: 9.0},
                sample_size=2,
            )
            return engine.run(experiment["experiment_id"])

        def build_graph() -> dict[str, object]:
            knowledge_graph = SoftwareKnowledgeGraph()
            knowledge_graph.add_repository(graph)
            return knowledge_graph.to_dict()

        controller = EvolutionController(root, indexer=IncrementalIndexer(project_root=root))
        metrics = {
            "research_planning_latency": _measure(
                lambda: research.generate_research_plan(problem),
                iterations,
            ),
            "architecture_analysis_latency": _measure(
                lambda: ArchitectureEvolutionEngine().analyze(root, graph),
                iterations,
            ),
            "experiment_execution_latency": _measure(run_experiment, iterations),
            "knowledge_graph_construction_latency": _measure(build_graph, iterations),
            "optimization_latency": _measure(
                lambda: optimizer.optimize({
                    "planning": {"latency_seconds": 1.1},
                    "caching": {"hit_ratio": 0.4},
                }),
                iterations,
            ),
            "evolution_cycle_latency": _measure(
                lambda: controller.run_cycle(symbol_graph=graph),
                iterations,
            ),
        }

    result: dict[str, object] = {
        "version": "4.0",
        "iterations": iterations,
        "metrics": metrics,
        "notes": (
            "Local microbenchmarks use a one-module project; timings depend on "
            "machine load and are not release-to-release performance claims."
        ),
    }
    output = Path(output_dir)
    history_path = output / "v40_benchmark_history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        history = []
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot load benchmark history {history_path}: {exc}") from exc
    if not isinstance(history, list):
        raise ValueError(f"Benchmark history {history_path} must contain a JSON list.")
    history.append(result)
    _write_json(history_path, history)
    _write_json(output / "v40_benchmark_results.json", result)
    _write_json(output / "v40_performance_report.json", {
        "version": "4.0",
        "benchmarks": metrics,
        "measurement_note": result["notes"],
    })
    return result


if __name__ == "__main__":
    print(json.dumps(run_benchmarks(), indent=2, sort_keys=True))
