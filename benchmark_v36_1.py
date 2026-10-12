"""Reproducible standard-library benchmark run for AutoDev 3.6.1."""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Callable

from core.cache_manager import CacheManager
from core.change_detector import RepositoryChangeDetector
from core.code_indexer import CodeIndexer
from core.context_builder import ContextBuilder
from core.doc_incremental_builder import DocIncrementalBuilder
from core.incremental_indexer import IncrementalIndexer
from core.orchestrator import Orchestrator
from core.performance_profiler import PerformanceProfiler
from core.test_selector import TestSelector

ROOT = Path(__file__).resolve().parent
BENCHMARK_DIR = ROOT / "memory" / "benchmarks"
SOURCE_COUNT = 1000
TEST_COUNT = 500
SYMBOLS_PER_FILE = 5
SOURCE_PADDING_BYTES = 4096


class _EmptyPlanner:
    def execute(self, context: dict) -> list:
        return []


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _samples(action: Callable[[], object], count: int) -> list[float]:
    values = []
    for _ in range(count):
        start = time.perf_counter()
        action()
        values.append(time.perf_counter() - start)
    return values


def _peak_traced_bytes(action: Callable[[], object]) -> int:
    tracemalloc.start()
    tracemalloc.reset_peak()
    action()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def _median(values: list[float]) -> float:
    return statistics.median(values)


def _deep_size(value: object, seen: set[int] | None = None) -> int:
    """Estimates retained Python-object bytes without double-counting references."""
    visited = seen if seen is not None else set()
    identity = id(value)
    if identity in visited:
        return 0
    visited.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(_deep_size(key, visited) + _deep_size(item, visited) for key, item in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(_deep_size(item, visited) for item in value)
    elif hasattr(value, "__dict__"):
        size += _deep_size(vars(value), visited)
    return size


def _measure(root: Path) -> dict:
    memory_dir = root / "memory"
    plan_path = memory_dir / "project_plan.json"
    state_path = memory_dir / "state.json"
    _write(
        plan_path,
        json.dumps({"project_name": "Benchmark", "total_days": 1, "phases": [{"day": 1}]}),
    )
    for index in range(SOURCE_COUNT):
        imports = f"from .module_{index - 1:03d} import function_{index - 1}\n" if index else ""
        padding = f'METADATA = "{"x" * SOURCE_PADDING_BYTES}"\n'
        _write(
            root / "src" / f"module_{index:03d}.py",
            imports
            + padding
            + "".join(
                f"def function_{index}_{symbol}():\n    return {index + symbol}\n\n"
                for symbol in range(SYMBOLS_PER_FILE)
            ),
        )
    for index in range(TEST_COUNT):
        _write(
            root / "tests" / f"test_module_{index:03d}.py",
            f"def test_module_{index}():\n    assert True\n",
        )

    orchestrator = Orchestrator(
        project_root=root,
        plan_path=plan_path,
        state_path=state_path,
        tasks_path=memory_dir / "tasks.json",
        log_dir=root / "logs",
        task_planner=_EmptyPlanner(),
    )
    orchestration_cold = _samples(orchestrator.run, 1)
    orchestration_warm = _samples(orchestrator.run, 3)
    indexer = orchestrator.incremental_indexer
    indexer.index_project(force_reindex=True, parallel=False)
    forced_full_index = _samples(
        lambda: indexer.index_project(force_reindex=True, parallel=False),
        5,
    )
    warm_stats_before = indexer.indexer.symbol_cache.statistics()
    warm_incremental_index = _samples(indexer.index_project, 10)
    warm_stats_after = indexer.indexer.symbol_cache.statistics()

    source_paths = sorted((root / "src").glob("*.py"))

    def build_symbol_graph() -> None:
        parser = CodeIndexer(
            project_root=root,
            output_path=memory_dir / "benchmark_graph.json",
            auto_load=False,
            cache_manager=CacheManager(memory_dir / "cache"),
        )
        for source in source_paths:
            parser.index_file(source)
        parser._resolve_cross_references()

    standalone_symbol_graph = _samples(build_symbol_graph, 5)
    graph_parser = CodeIndexer(
        project_root=root,
        output_path=memory_dir / "incremental_graph.json",
        auto_load=False,
        cache_manager=CacheManager(memory_dir / "cache"),
    )
    graph_parser.graph = indexer.graph
    from core.incremental_symbol_cache import IncrementalSymbolCache

    symbol_cache = IncrementalSymbolCache(
        project_root=root,
        graph=indexer.graph,
        parser=lambda path, content: graph_parser.index_file(path, content=content),
    )
    rebuild_samples = []
    mutable_source = source_paths[-1]
    for index in range(10):
        _write(
            mutable_source,
            "".join(
                f"def function_{SOURCE_COUNT - 1}_{symbol}():\n    return {index + symbol}\n\n"
                for symbol in range(SYMBOLS_PER_FILE)
            ),
        )
        start = time.perf_counter()
        symbol_cache.update(mutable_source, force=True)
        rebuild_samples.append(time.perf_counter() - start)

    detector = RepositoryChangeDetector(root)
    detector.snapshot()
    cold_context = []
    for index in range(5):
        cold_context_builder = ContextBuilder(
            project_root=root,
            plan_path=plan_path,
            state_path=state_path,
            change_detector=detector,
            cache_dir=root / f"cold_context_cache_{index}",
        )
        start = time.perf_counter()
        cold_context_builder.scan_project_workspace()
        cold_context.append(time.perf_counter() - start)
    context_builder = ContextBuilder(
        project_root=root,
        plan_path=plan_path,
        state_path=state_path,
        change_detector=detector,
        cache_dir=root / "warm_context_cache",
    )
    context_builder.scan_project_workspace()
    detector.snapshot()
    warm_context = _samples(context_builder.scan_project_workspace, 5)

    document = root / "docs" / "benchmark.md"
    sections = {
        f"section_{index}": f"Generated section content {index}.\n" * 20
        for index in range(100)
    }
    doc_builder = DocIncrementalBuilder()
    doc_builder.update_document(document, sections)
    document_content = document.read_text(encoding="utf-8")
    full_document_rewrite = _samples(
        lambda: document.write_text(document_content, encoding="utf-8"),
        50,
    )
    incremental_document = _samples(
        lambda: doc_builder.update_document(document, sections),
        50,
    )

    selector = TestSelector(project_root=root)
    selection_start = time.perf_counter()
    selected_tests = selector.select_tests(["src/module_100.py"])
    test_discovery_seconds = time.perf_counter() - selection_start
    cache_stats = indexer.indexer.symbol_cache.statistics()
    warm_hits = warm_stats_after["hits"] - warm_stats_before["hits"]
    warm_misses = warm_stats_after["misses"] - warm_stats_before["misses"]
    warm_observations = warm_hits + warm_misses
    cold_memory_peak = _peak_traced_bytes(
        lambda: indexer.index_project(force_reindex=True, parallel=False)
    )
    warm_memory_peak = _peak_traced_bytes(indexer.index_project)
    cache_path = memory_dir / "cache" / "symbol_graph" / "symbol_graph.json"
    graph = indexer.graph
    graph_core_bytes = _deep_size(
        {name: value for name, value in vars(graph).items() if name != "file_hashes"}
    )
    symbol_cache_state = {
        name: value
        for name, value in vars(indexer.indexer.symbol_cache).items()
        if name not in {"graph", "parser"}
    }
    cache_bookkeeping_bytes = (
        _deep_size(graph.file_hashes)
        + _deep_size(symbol_cache_state)
        + _deep_size(indexer.indexer.cache_manager.metadata)
    )

    measurements = {
        "forced_full_index": forced_full_index,
        "warm_incremental_index": warm_incremental_index,
        "standalone_symbol_graph_generation": standalone_symbol_graph,
        "incremental_symbol_graph_update": rebuild_samples,
        "cold_context_build": cold_context,
        "warm_context_build": warm_context,
        "full_document_rewrite": full_document_rewrite,
        "incremental_document_noop": incremental_document,
        "cold_orchestration": orchestration_cold,
        "warm_orchestration": orchestration_warm,
        "test_discovery": [test_discovery_seconds],
    }
    index_speedup = (
        1 - _median(warm_incremental_index) / _median(forced_full_index)
    ) * 100
    symbol_graph_speedup = (
        1 - _median(rebuild_samples) / _median(standalone_symbol_graph)
    ) * 100
    context_speedup = (1 - _median(warm_context) / _median(cold_context)) * 100
    documentation_speedup = (
        1 - _median(incremental_document) / _median(full_document_rewrite)
    ) * 100
    cache_observation_count = cache_stats["hits"] + cache_stats["misses"]

    return {
        "version": "3.6.1",
        "environment": {
            "python": __import__("platform").python_version(),
            "platform": __import__("platform").platform(),
        },
        "workload": {
            "source_files": SOURCE_COUNT,
            "symbols_per_source_file": SYMBOLS_PER_FILE,
            "expected_source_symbols": SOURCE_COUNT * SYMBOLS_PER_FILE,
            "source_padding_bytes": SOURCE_PADDING_BYTES,
            "test_files": TEST_COUNT,
            "documentation_bytes": len(document_content.encode("utf-8")),
            "managed_sections": len(sections),
        },
        "measurements": measurements,
        "comparison": {
            "index_speedup_percent": round(index_speedup, 2),
            "symbol_graph_speedup_percent": round(symbol_graph_speedup, 2),
            "context_speedup_percent": round(context_speedup, 2),
            "documentation_speedup_percent": round(documentation_speedup, 2),
            "warm_cache_hit_ratio": (
                warm_hits / warm_observations if warm_observations else 0.0
            ),
            "warm_cache_miss_ratio": (
                warm_misses / warm_observations if warm_observations else 0.0
            ),
            "cache_hit_ratio": (
                cache_stats["hits"] / cache_observation_count
                if cache_observation_count
                else 0.0
            ),
            "cache_miss_ratio": (
                cache_stats["misses"] / cache_observation_count
                if cache_observation_count
                else 0.0
            ),
            "average_cache_rebuild_seconds": statistics.mean(rebuild_samples),
            "cold_orchestration_seconds": orchestration_cold[0],
            "warm_orchestration_median_seconds": _median(orchestration_warm),
            "development_iteration_speedup_percent": round(
                (1 - _median(orchestration_warm) / orchestration_cold[0]) * 100,
                2,
            ),
            "incremental_execution_seconds": _median(warm_incremental_index),
            "cold_index_peak_traced_bytes": cold_memory_peak,
            "warm_index_peak_traced_bytes": warm_memory_peak,
            "warm_peak_as_percent_of_cold_peak": (
                round(100 * warm_memory_peak / cold_memory_peak, 2)
                if cold_memory_peak
                else 0.0
            ),
            "repository_cache_bookkeeping_bytes": cache_bookkeeping_bytes,
            "repository_graph_core_bytes": graph_core_bytes,
            "repository_cache_overhead_percent": (
                round(100 * cache_bookkeeping_bytes / graph_core_bytes, 2)
                if graph_core_bytes
                else 0.0
            ),
            "symbol_cache_file_bytes": cache_path.stat().st_size,
        },
        "test_selection": {
            "available_test_files": TEST_COUNT,
            "selected_test_files": len(selected_tests),
            "selected_paths": selected_tests,
            "fallback_to_full_suite": selector.last_selection.fallback_to_full_suite,
            "discovery_seconds": test_discovery_seconds,
        },
        "measurement_notes": [
            "Symbol graph baseline parses all source files into a new graph; the isolated incremental sample reparses one changed file in the cached graph without repository scanning or persistence.",
            "Tracemalloc values are peak Python allocations for the indexing operation, not process RSS.",
            "Cache-overhead percentage estimates retained Python bookkeeping and per-file hashes relative to the SymbolGraph object model; it excludes interpreter allocator overhead and disk-cache size.",
            "Orchestration timings use Orchestrator.run with an injected no-op task planner and no task execution.",
            "Synthetic workload measurements are environment-specific and are not a guarantee for other repositories.",
        ],
        "cache_statistics": {
            **cache_stats,
            "warm_hits": warm_hits,
            "warm_misses": warm_misses,
            "warm_hit_ratio": (
                warm_hits / warm_observations if warm_observations else 0.0
            ),
            "warm_miss_ratio": (
                warm_misses / warm_observations if warm_observations else 0.0
            ),
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="autodev-v361-benchmark-") as directory:
        results = _measure(Path(directory))

    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    results_path = BENCHMARK_DIR / "v36_1_benchmark_results.json"
    history_path = BENCHMARK_DIR / "v36_1_benchmark_history.json"
    legacy_history_path = BENCHMARK_DIR / "benchmark_history.json"
    report_path = BENCHMARK_DIR / "performance_report.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    profiler = PerformanceProfiler(
        history_file=history_path,
        report_file=report_path,
    )
    profiler.history = {}
    for name, samples in results["measurements"].items():
        for duration in samples:
            profiler.record_duration(name, duration)
    legacy_history_path.write_text(
        json.dumps(profiler.history, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    profiler.record_memory_usage(
        "cold_index_peak_traced_bytes",
        results["comparison"]["cold_index_peak_traced_bytes"],
    )
    profiler.record_memory_usage(
        "warm_index_peak_traced_bytes",
        results["comparison"]["warm_index_peak_traced_bytes"],
    )
    profiler.save_report()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["comparison"] = results["comparison"]
    report["test_selection"] = results["test_selection"]
    report["cache_statistics"] = results["cache_statistics"]
    report["measurement_notes"] = results["measurement_notes"]
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results["comparison"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
