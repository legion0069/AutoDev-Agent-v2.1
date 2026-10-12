"""Measure Version 3.8 collaboration operations and write a JSON result bundle."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
import tracemalloc
from itertools import count
from pathlib import Path
from typing import Any, Callable

from core.agent_bus import AgentBus
from core.blackboard import Blackboard
from core.capability_manager import AgentCapabilityManager
from core.collaboration_engine import CollaborationEngine
from core.consensus_engine import ConsensusEngine
from core.incremental_symbol_cache import IncrementalSymbolCache
from core.multi_agent.agent_registry import AgentDescriptor, AgentRegistry, AgentRole
from core.multi_agent_runtime import MultiAgentRuntime
from core.parallel_scheduler import ParallelTaskScheduler
from core.task_negotiation import TaskNegotiationEngine


def _measure(operation: Callable[[], Any], iterations: int) -> dict[str, float]:
    durations = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        durations.append(time.perf_counter() - started)
    return {
        "mean_seconds": round(statistics.fmean(durations), 8),
        "median_seconds": round(statistics.median(durations), 8),
        "p95_seconds": round(sorted(durations)[max(0, int(len(durations) * 0.95) - 1)], 8),
        "iterations": iterations,
    }


def run_benchmarks(
    output_dir: str | Path = "memory/benchmarks",
    iterations: int = 30,
) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be at least one")
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    tracemalloc.start()
    initial_memory, _ = tracemalloc.get_traced_memory()
    registry = AgentRegistry()
    capabilities = AgentCapabilityManager(registry)
    runtime = MultiAgentRuntime(
        registry=registry,
        capability_manager=capabilities,
    )
    runtime.register_agent(
        AgentDescriptor(
            agent_id="benchmark-agent",
            name="Benchmark Agent",
            role=AgentRole.BACKEND_ENGINEER,
            capabilities=["implementation"],
            max_workload=2,
        ),
        handler=lambda task: task,
    )
    negotiator = TaskNegotiationEngine(capabilities)
    bus = AgentBus()
    blackboard = Blackboard()
    collaboration = CollaborationEngine()
    consensus = ConsensusEngine()
    task = {"id": "benchmark-task", "title": "Implement benchmark"}
    proposal_ids = count()
    negotiation = _measure(
        lambda: negotiator.negotiate(task, ["implementation"]),
        iterations,
    )
    dispatch = _measure(
        lambda: runtime.dispatch(
            {"id": "benchmark-dispatch"},
            ["implementation"],
            record_metrics=False,
        ),
        iterations,
    )
    collaboration_latency = _measure(
        lambda: collaboration.plan(
            [{"id": "plan-task", "title": "Plan task", "dependencies": []}]
        ),
        iterations,
    )
    consensus_latency = _measure(
        lambda: consensus.decide(
            [
                {"reviewer_id": "architect", "decision": "approve"},
                {"reviewer_id": "tester", "decision": "approve"},
            ],
            proposal_id=f"benchmark-{next(proposal_ids)}",
        ),
        iterations,
    )
    blackboard_latency = _measure(
        lambda: (
            blackboard.write("benchmark", {"sequence": 1}),
            blackboard.read("benchmark"),
        ),
        iterations,
    )

    message_count = max(100, iterations * 10)
    message_started = time.perf_counter()
    for sequence in range(message_count):
        bus.publish("STATUS", "benchmark", "receiver", {"sequence": sequence})
    message_duration = time.perf_counter() - message_started

    task_count = max(8, iterations)
    serial_started = time.perf_counter()
    for _ in range(task_count):
        time.sleep(0.001)
    serial_duration = time.perf_counter() - serial_started
    parallel_tasks = [
        {
            "id": f"parallel-{index:04d}",
            "function": lambda _: time.sleep(0.001),
            "dependencies": [],
            "resources": [f"resource-{index:04d}"],
        }
        for index in range(task_count)
    ]
    parallel_started = time.perf_counter()
    CollaborationEngine().execute(parallel_tasks, max_workers=4)
    parallel_duration = time.perf_counter() - parallel_started

    with tempfile.TemporaryDirectory(prefix="autodev-v38-cache-") as temp_dir:
        project_root = Path(temp_dir)
        source_paths = []
        for index in range(20):
            source = project_root / f"module_{index:02d}.py"
            source.write_text(f"def item_{index}():\n    return {index}\n", encoding="utf-8")
            source_paths.append(source)
        cold_cache = IncrementalSymbolCache(project_root=project_root)
        cold_cache.load()
        for source in source_paths:
            cold_cache.update(source)
        cold_cache.save()
        warm_cache = IncrementalSymbolCache(project_root=project_root)
        warm_cache.load()
        for source in source_paths:
            warm_cache.has_changed(source)
            warm_cache.update(source)
        cache_stats = warm_cache.statistics()

    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    runtime.close()
    result = {
        "version": "3.8",
        "measurement": "single local run; values are descriptive, not performance guarantees",
        "iterations": iterations,
        "metrics": {
            "agent_dispatch_latency": dispatch,
            "task_negotiation_latency": negotiation,
            "collaboration_planning_latency": collaboration_latency,
            "consensus_latency": consensus_latency,
            "blackboard_read_write_latency": blackboard_latency,
            "parallel_scheduler": {
                "task_count": task_count,
                "serial_seconds": round(serial_duration, 8),
                "parallel_seconds": round(parallel_duration, 8),
                "speedup": round(serial_duration / max(parallel_duration, 1e-12), 4),
                "efficiency": round(
                    serial_duration / max(parallel_duration * 4, 1e-12),
                    4,
                ),
            },
            "message_throughput_per_second": round(
                message_count / max(message_duration, 1e-12), 2
            ),
            "message_count": message_count,
            "warm_cache_hit_ratio": cache_stats["hit_ratio"],
            "warm_cache_statistics": cache_stats,
            "tracemalloc_peak_overhead_bytes": max(0, peak_memory - initial_memory),
        },
    }
    result_path = output_root / "v38_multi_agent_results.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    history_path = output_root / "v38_benchmark_history.json"
    history = []
    if history_path.is_file():
        try:
            loaded = json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as err:
            raise RuntimeError(
                f"Could not load Version 3.8 benchmark history at {history_path}"
            ) from err
        if not isinstance(loaded, list):
            raise ValueError(f"Version 3.8 benchmark history must be a list: {history_path}")
        history = loaded
    history.append(result)
    history_path.write_text(
        json.dumps(history[-100:], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output-dir", default="memory/benchmarks")
    args = parser.parse_args()
    result = run_benchmarks(args.output_dir, args.iterations)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
