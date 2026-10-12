"""
performance_profiler.py - Performance Profiling Framework for AutoDev (v3.6.1)

Benchmarks various subsystems and tracks performance history.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import tempfile
import threading
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("AutoDev.PerformanceProfiler")

@dataclass
class PerformanceStats:
    """Statistical metrics for a profiled operation."""
    min: float
    max: float
    mean: float
    median: float
    p95: float
    count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min": round(self.min, 4),
            "max": round(self.max, 4),
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "p95": round(self.p95, 4),
            "count": self.count
        }

@dataclass
class PerformanceReport:
    """Comprehensive performance report across subsystems."""
    timestamp: float
    subsystems: Dict[str, PerformanceStats]
    memory_usage_bytes: Dict[str, int] = field(default_factory=dict)
    cache_statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "subsystems": {
                name: stats.to_dict()
                for name, stats in sorted(self.subsystems.items())
            },
            "memory_usage_bytes": dict(sorted(self.memory_usage_bytes.items())),
            "cache_statistics": self.cache_statistics,
        }

class PerformanceProfiler:
    """
    Benchmarks AutoDev subsystems and manages performance history.
    """

    HISTORY_FILE = Path("memory/benchmarks/history.json")
    REPORT_FILE = Path("memory/benchmarks/performance_report.json")

    def __init__(
        self,
        history_file: Optional[Union[str, Path]] = None,
        report_file: Optional[Union[str, Path]] = None,
        cache_manager: Optional[Any] = None,
    ) -> None:
        self.history_file = Path(history_file).resolve() if history_file else self.HISTORY_FILE
        self.report_file = Path(report_file).resolve() if report_file else self.REPORT_FILE
        self.cache_manager = cache_manager
        self.history: Dict[str, List[float]] = {}
        self.memory_usage_bytes: Dict[str, int] = {}
        self._lock = threading.RLock()
        self._load_history()

    def _load_history(self) -> None:
        if self.history_file.exists():
            try:
                self.history = json.loads(self.history_file.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as err:
                logger.warning("Failed to load performance history: %s", err)

    def _save_history(self) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.history_file.parent, delete=False
        ) as temp_file:
            json.dump(self.history, temp_file, indent=2, sort_keys=True)
            temp_path = Path(temp_file.name)
        temp_path.replace(self.history_file)

    def record_duration(self, subsystem: str, duration: float) -> None:
        """Records a single duration measurement for a subsystem."""
        if not subsystem:
            raise ValueError("Subsystem name must not be empty.")
        if duration < 0:
            raise ValueError("Duration must not be negative.")
        with self._lock:
            self.history.setdefault(subsystem, []).append(float(duration))
            del self.history[subsystem][:-1000]
            self._save_history()

    def record_memory_usage(self, subsystem: str, usage_bytes: int) -> None:
        """Records a non-negative peak memory delta for a subsystem."""
        if usage_bytes < 0:
            raise ValueError("Memory usage must not be negative.")
        with self._lock:
            self.memory_usage_bytes[subsystem] = int(usage_bytes)

    def profile_subsystem(self, name: str):
        """Decorator or context manager to profile a subsystem."""
        class ProfilerContext:
            def __init__(self, profiler: PerformanceProfiler, subsystem: str):
                self.profiler = profiler
                self.subsystem = subsystem
                self.start_time = 0.0
                self._owns_tracemalloc = False
                self._starting_memory = 0

            def __enter__(self):
                self.start_time = time.perf_counter()
                if not tracemalloc.is_tracing():
                    tracemalloc.start()
                    self._owns_tracemalloc = True
                self._starting_memory = tracemalloc.get_traced_memory()[0]
                tracemalloc.reset_peak()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.perf_counter() - self.start_time
                self.profiler.record_duration(self.subsystem, duration)
                peak_memory = max(
                    0,
                    tracemalloc.get_traced_memory()[1] - self._starting_memory,
                )
                self.profiler.record_memory_usage(self.subsystem, peak_memory)
                if self._owns_tracemalloc:
                    tracemalloc.stop()

        return ProfilerContext(self, name)

    def generate_report(self) -> PerformanceReport:
        """Calculates statistics and generates a performance report."""
        stats_map = {}
        for subsystem, durations in sorted(self.history.items()):
            if not durations:
                continue

            sorted_durations = sorted(durations)
            count = len(durations)
            mean = sum(durations) / count
            median = statistics.median(sorted_durations)
            p95 = sorted_durations[max(0, math.ceil(count * 0.95) - 1)]

            stats_map[subsystem] = PerformanceStats(
                min=min(durations),
                max=max(durations),
                mean=mean,
                median=median,
                p95=p95,
                count=count
            )

        cache_stats = self.cache_manager.stats() if self.cache_manager else {}
        return PerformanceReport(
            timestamp=time.time(),
            subsystems=stats_map,
            memory_usage_bytes=dict(sorted(self.memory_usage_bytes.items())),
            cache_statistics=cache_stats,
        )

    def save_report(
        self,
        output_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Generates and atomically writes performance_report.json."""
        target = Path(output_path).resolve() if output_path else self.report_file
        report = self.generate_report()
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent, delete=False
        ) as temp_file:
            json.dump(report.to_dict(), temp_file, indent=2, sort_keys=True)
            temp_path = Path(temp_file.name)
        temp_path.replace(target)
        return target

    def generate_dashboard(self, output_path: str = "performance_dashboard.json") -> None:
        """Generates a detailed performance dashboard JSON."""
        from core.cache_manager import CacheManager
        cache_manager = CacheManager()
        cache_stats = cache_manager.get_stats()
        
        report = self.generate_report()
        
        dashboard = {
            "version": "3.6.1",
            "generated_at": time.time(),
            "subsystems": report.to_dict()["subsystems"],
            "cache": {
                "total_size_bytes": cache_stats["total_size_bytes"],
                "cache_count": cache_stats["cache_count"],
                "details": cache_stats["caches"]
            },
            "summary": {
                "avg_indexing_time": report.subsystems.get("Indexing", PerformanceStats(0,0,0,0,0,0)).mean if "Indexing" in report.subsystems else 0,
                "avg_warm_indexing_time": report.subsystems.get("Warm_Indexing", PerformanceStats(0,0,0,0,0,0)).mean if "Warm_Indexing" in report.subsystems else 0,
                "hit_ratio_overall": self._calculate_overall_hit_ratio(cache_stats)
            }
        }
        
        Path(output_path).write_text(json.dumps(dashboard, indent=2), encoding="utf-8")

    def _calculate_overall_hit_ratio(self, cache_stats: Dict[str, Any]) -> float:
        total_hits = 0
        total_misses = 0
        for cache in cache_stats["caches"].values():
            total_hits += cache.get("hit_count", 0)
            total_misses += cache.get("miss_count", 0)
        
        if (total_hits + total_misses) == 0:
            return 0.0
        return total_hits / (total_hits + total_misses)
