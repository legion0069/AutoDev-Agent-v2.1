"""Benchmark deterministic Version 3.7 reasoning and decision support."""

from __future__ import annotations

import json
import platform
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

from core.decision_engine import DecisionEngine
from core.explainability import ExplainabilityEngine
from core.hypothesis_engine import HypothesisEngine
from core.knowledge_reasoner import KnowledgeReasoner
from core.planning_revision import PlanningRevisionEngine
from core.reasoning_engine import ReasoningEngine


def _measure(operation: Callable[[], Any], iterations: int) -> dict[str, Any]:
    samples = []
    tracemalloc.start()
    try:
        for _ in range(iterations):
            started = time.perf_counter()
            operation()
            samples.append(time.perf_counter() - started)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "samples_seconds": samples,
        "median_seconds": statistics.median(samples) if samples else 0.0,
        "peak_traced_bytes": peak_bytes,
    }


def run_benchmarks(
    output_dir: str | Path = "memory/benchmarks",
    iterations: int = 30,
) -> dict[str, Any]:
    """Runs cold/warm samples, records cache ratios, and persists JSON artifacts."""
    if iterations < 1:
        raise ValueError("iterations must be at least one")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autodev-v37-bench-") as temporary:
        root = Path(temporary)
        reasoning = ReasoningEngine(root)
        decision = DecisionEngine(project_root=str(root))
        hypotheses = HypothesisEngine(project_root=root)
        knowledge = KnowledgeReasoner(
            sources=[
                {
                    "id": f"learning-{index:03d}",
                    "summary": f"Cache invalidation issue {index} was fixed with content hashes.",
                }
                for index in range(100)
            ],
            project_root=root,
        )
        planner = PlanningRevisionEngine()
        explainability = ExplainabilityEngine()

        goal = "Improve deterministic cache invalidation and explainable planning."
        context = {"files": ["core/cache_manager.py"], "constraints": ["stdlib only"]}
        options = [
            {"name": "focused", "benefit": 0.8, "evidence": 0.9, "risk": 0.1},
            {"name": "broad", "benefit": 0.9, "evidence": 0.5, "risk": 0.7},
        ]
        plan = [
            {"id": f"task-{index:03d}", "dependencies": [f"task-{index - 1:03d}"] if index else []}
            for index in range(100)
        ]
        reasoning.reason(goal, context)
        decision.rank_options(options)
        hypotheses.generate(goal, limit=5)
        knowledge.reason("cache invalidation content hashes")

        measurements = {
            "reasoning_cold": _measure(lambda: ReasoningEngine(root / "cold-reasoning").reason(goal, context), 1),
            "reasoning_warm": _measure(lambda: reasoning.reason(goal, context), iterations),
            "decision_cold": _measure(lambda: DecisionEngine(project_root=str(root / "cold-decision")).rank_options(options), 1),
            "decision_warm": _measure(lambda: decision.rank_options(options), iterations),
            "hypothesis_cold": _measure(lambda: HypothesisEngine(project_root=root / "cold-hypotheses").generate(goal, limit=5), 1),
            "hypothesis_warm": _measure(lambda: hypotheses.generate(goal, limit=5), iterations),
            "knowledge_cold": _measure(lambda: KnowledgeReasoner(sources=knowledge.sources, project_root=root / "cold-knowledge").reason("cache invalidation content hashes"), 1),
            "knowledge_warm": _measure(lambda: knowledge.reason("cache invalidation content hashes"), iterations),
            "planning_100_tasks": _measure(lambda: planner.optimize(plan), iterations),
            "explainability_100_tasks": _measure(lambda: explainability.explain_plan(plan), iterations),
        }
        cache_statistics = {
            "reasoning": reasoning.statistics(),
            "decision": decision.statistics(),
            "hypotheses": hypotheses.statistics()["cache"],
            "knowledge": knowledge.statistics(),
        }
        total_requests = sum(
            int(values["hits"]) + int(values["misses"])
            for values in cache_statistics.values()
        )
        total_hits = sum(int(values["hits"]) for values in cache_statistics.values())
        cache_hit_ratio = total_hits / total_requests if total_requests else 0.0
        result = {
            "version": "3.7",
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "iterations": iterations,
            "workload": {
                "planned_tasks": len(plan),
                "knowledge_records": len(knowledge.sources),
                "strategy_options": len(options),
            },
            "measurements": measurements,
            "cache_statistics": cache_statistics,
            "summary": {
                "warm_cache_hit_ratio": round(cache_hit_ratio, 6),
                "reasoning_speedup_percent": _speedup(
                    measurements["reasoning_cold"]["median_seconds"],
                    measurements["reasoning_warm"]["median_seconds"],
                ),
                "decision_speedup_percent": _speedup(
                    measurements["decision_cold"]["median_seconds"],
                    measurements["decision_warm"]["median_seconds"],
                ),
            },
            "measurement_notes": [
                "Cold and warm measurements use the same deterministic input and a temporary cache directory.",
                "Planning and explainability measurements are uncached baseline operations.",
                "Peak memory is tracemalloc Python allocation, not process resident memory.",
                "These microbenchmarks do not constitute end-to-end orchestration or repository-wide speedup measurements.",
            ],
        }

    results_path = output / "v37_reasoning_benchmark_results.json"
    results_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    history_path = output / "v37_benchmark_history.json"
    history = _read_history(history_path)
    history.append({"timestamp": time.time(), "summary": result["summary"], "measurements": {
        name: {
            "median_seconds": values["median_seconds"],
            "peak_traced_bytes": values["peak_traced_bytes"],
        }
        for name, values in measurements.items()
    }})
    history = history[-100:]
    history_path.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    combined_history_path = output / "benchmark_history.json"
    combined_history = _read_object(combined_history_path)
    for name, values in measurements.items():
        combined_history.setdefault(f"v37_{name}", []).append(values["median_seconds"])
        combined_history[f"v37_{name}"] = combined_history[f"v37_{name}"][-1000:]
    combined_history_path.write_text(
        json.dumps(combined_history, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = output / "performance_report.json"
    report = _read_object(report_path)
    report["v37_reasoning_benchmarks"] = {
        "summary": result["summary"],
        "measurements": {
            name: {
                "median_seconds": values["median_seconds"],
                "peak_traced_bytes": values["peak_traced_bytes"],
            }
            for name, values in measurements.items()
        },
        "cache_statistics": cache_statistics,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _speedup(cold: float, warm: float) -> float:
    return round((1.0 - warm / cold) * 100.0, 2) if cold > 0 else 0.0


def _read_history(path: Path) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except FileNotFoundError:
        return []


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


if __name__ == "__main__":
    print(json.dumps(run_benchmarks(), indent=2, sort_keys=True))
