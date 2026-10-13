"""Stage telemetry interpretation for continuous performance improvement."""

from __future__ import annotations

import sys
import time
from typing import Any, Mapping


class PerformanceEvolutionEngine:
    """Normalizes runtime metrics and suggests measured performance investigations."""

    STAGES = ("execution", "planning", "scheduling", "learning")

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []

    def capture(
        self,
        *,
        cache_manager: Any = None,
        stage_metrics: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Captures process CPU/RSS and optional cache and stage telemetry."""
        cpu: dict[str, Any] = {"process_cpu_seconds": time.process_time()}
        memory: dict[str, Any] = {}
        try:
            import resource
        except ImportError:
            memory["peak_bytes"] = None
            memory["availability"] = "resource module unavailable"
        else:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            multiplier = 1 if sys.platform == "darwin" else 1024
            memory["peak_bytes"] = int(usage.ru_maxrss * multiplier)
            cpu["user_seconds"] = usage.ru_utime
            cpu["system_seconds"] = usage.ru_stime

        cache: dict[str, Any] = {}
        if cache_manager is not None:
            stats = cache_manager.get_stats()
            total_hits = sum(
                int(item.get("hit_count", 0))
                for item in stats.get("caches", {}).values()
            )
            total_misses = sum(
                int(item.get("miss_count", 0))
                for item in stats.get("caches", {}).values()
            )
            total = total_hits + total_misses
            cache = {
                "cache_count": stats.get("cache_count", 0),
                "size_bytes": stats.get("total_size_bytes", 0),
                "hit_count": total_hits,
                "miss_count": total_misses,
                "hit_ratio": total_hits / total if total else 0.0,
            }
        return self.analyze({
            "cpu": cpu,
            "memory": memory,
            "cache": cache,
            **dict(stage_metrics or {}),
        })

    def analyze(self, metrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = dict(metrics or {})
        cpu = data.get("cpu", {})
        memory = data.get("memory", {})
        cache = data.get("cache", {})
        stages = {
            stage: self._stage_metrics(data.get(stage, {}))
            for stage in self.STAGES
        }
        recommendations = []
        cpu_seconds = cpu.get("process_cpu_seconds") if isinstance(cpu, Mapping) else None
        if isinstance(cpu_seconds, (int, float)) and cpu_seconds > 60.0:
            recommendations.append({
                "domain": "cpu",
                "priority": "medium",
                "action": "Profile CPU-heavy stages and compare equivalent workloads.",
                "evidence": {"process_cpu_seconds": cpu_seconds},
            })
        for stage, values in stages.items():
            latency = values.get("latency_seconds")
            if isinstance(latency, (int, float)) and latency > 1.0:
                recommendations.append({
                    "domain": stage,
                    "priority": "high" if latency > 5.0 else "medium",
                    "action": f"Profile the {stage} stage and benchmark a behavior-preserving alternative.",
                    "evidence": {"latency_seconds": latency},
                })
        hit_ratio = cache.get("hit_ratio") if isinstance(cache, Mapping) else None
        if isinstance(hit_ratio, (int, float)) and hit_ratio < 0.5:
            recommendations.append({
                "domain": "cache",
                "priority": "medium",
                "action": "Inspect cache-key stability and invalidation frequency.",
                "evidence": {"hit_ratio": hit_ratio},
            })
        peak = memory.get("peak_bytes") if isinstance(memory, Mapping) else None
        if isinstance(peak, (int, float)) and peak > 512 * 1024 * 1024:
            recommendations.append({
                "domain": "memory",
                "priority": "high",
                "action": "Profile large allocations and bound retained histories.",
                "evidence": {"peak_bytes": peak},
            })
        record = {
            "cpu": dict(cpu) if isinstance(cpu, Mapping) else {},
            "memory": dict(memory) if isinstance(memory, Mapping) else {},
            "cache": dict(cache) if isinstance(cache, Mapping) else {},
            "stages": stages,
            "recommendations": sorted(
                recommendations,
                key=lambda item: (
                    0 if item["priority"] == "high" else 1,
                    item["domain"],
                    item["action"],
                ),
            ),
        }
        self.history.append(record)
        return record

    @staticmethod
    def _stage_metrics(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return {
                key: value[key]
                for key in ("latency_seconds", "operations", "error_rate", "throughput")
                if key in value
            }
        if isinstance(value, (int, float)):
            return {"latency_seconds": float(value)}
        return {}
