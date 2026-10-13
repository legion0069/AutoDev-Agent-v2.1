"""Standard-library microbenchmarks for AutoDev V3.10 memory intelligence."""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.documentation_intelligence import DocumentationIntelligence
from core.engineering_memory import EngineeringMemory
from core.engineering_search import EngineeringSearchEngine
from core.experience_engine import ExperienceEngine
from core.knowledge_consolidation import KnowledgeConsolidationEngine
from core.knowledge_graph import KnowledgeGraph
from core.memory_controller import MemoryController
from core.memory_ranking import MemoryRankingEngine


def _measure(operation: Callable[[], object], iterations: int = 5) -> dict[str, float | int]:
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


def run_benchmarks(output_dir: Path | None = None) -> dict[str, object]:
    target = output_dir or ROOT / "memory" / "benchmarks"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autodev-v310-benchmark-") as temporary:
        workspace = Path(temporary)
        (workspace / "README.md").write_text(
            "# Memory intelligence\n\n## Cache\nReuse engineering memory for cache decisions.\n",
            encoding="utf-8",
        )
        memory = EngineeringMemory(workspace)
        controller = MemoryController(workspace, memory=memory)
        for index in range(20):
            controller.record_task_outcome({
                "type": "task",
                "task_id": f"task-{index}",
                "title": f"Cache engineering result {index}",
                "description": "Engineering memory search and retrieval benchmark.",
                "success": index % 4 != 0,
                "solution": "Use deterministic cache keys and bounded storage.",
                "topic": "cache",
                "importance": 5 + index % 6,
            })

        graph = KnowledgeGraph()
        for index in range(20):
            graph.add_node("module", f"module:{index:02}", f"module {index:02}")
            if index:
                graph.add_edge(f"module:{index - 1:02}", f"module:{index:02}", "depends_on")
        ranking = MemoryRankingEngine()
        experiences = ExperienceEngine(memory)
        consolidation = KnowledgeConsolidationEngine(memory)
        search = EngineeringSearchEngine(memory, graph, ranking_engine=ranking)
        docs = DocumentationIntelligence(workspace, memory, graph)

        metrics = {
            "memory_storage_latency": _measure(
                lambda: memory.store(
                    {"type": "benchmark", "title": "Storage benchmark", "value": 1},
                    record_id="benchmark-storage",
                )
            ),
            "engineering_search_latency": _measure(lambda: search.search("cache engineering", limit=10)),
            "experience_retrieval_latency": _measure(lambda: experiences.retrieve("cache", limit=10)),
            "context_assembly_latency": _measure(lambda: controller.retrieve_context("cache", max_items=8)),
            "memory_ranking_latency": _measure(lambda: ranking.rank(memory.records(), "cache")),
            "knowledge_graph_traversal_latency": _measure(
                lambda: graph.traverse("module:00", max_depth=10)
            ),
            "knowledge_consolidation_latency": _measure(lambda: consolidation.consolidate()),
            "documentation_analysis_latency": _measure(lambda: docs.analyze()),
            "end_to_end_memory_cycle_latency": _measure(
                lambda: (
                    controller.record_task_outcome({
                        "type": "task",
                        "task_id": "cycle-task",
                        "title": "Cache memory cycle",
                        "success": True,
                        "summary": "End-to-end benchmark record.",
                    }),
                    controller.retrieve_context("cache memory"),
                    controller.status(),
                )
            ),
        }

    results = {
        "version": "3.10",
        "iterations": 5,
        "metrics": dict(sorted(metrics.items())),
        "notes": "Local temporary-workspace microbenchmarks; timings vary by host and are not release performance claims.",
    }
    history_path = target / "v310_benchmark_history.json"
    history: list[dict[str, object]] = []
    if history_path.exists():
        loaded = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError(f"Benchmark history must contain a JSON list: {history_path}")
        history = loaded
    history.append(results)
    (target / "v310_benchmark_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    history_path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "version": "3.10",
        "benchmark_count": len(metrics),
        "metrics": {
            name: {
                "mean_seconds": values["mean_seconds"],
                "median_seconds": values["median_seconds"],
                "min_seconds": values["min_seconds"],
                "max_seconds": values["max_seconds"],
            }
            for name, values in metrics.items()
        },
        "notes": results["notes"],
    }
    (target / "v310_performance_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


if __name__ == "__main__":
    print(json.dumps(run_benchmarks(), indent=2, sort_keys=True))
