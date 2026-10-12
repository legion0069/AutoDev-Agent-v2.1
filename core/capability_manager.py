"""Deterministic capability and performance profile management for agents."""

from __future__ import annotations

import threading
from typing import Any, Optional

from core.multi_agent.agent_registry import AgentDescriptor, AgentRegistry


class AgentCapabilityManager:
    """Indexes skills, languages, domains, accuracy, and preferred workloads."""

    def __init__(self, registry: Optional[AgentRegistry] = None) -> None:
        self.registry = registry or AgentRegistry()
        self._lock = threading.RLock()
        self._profiles: dict[str, dict[str, Any]] = {}

    def register(
        self,
        agent_id: str,
        skills: Optional[list[str]] = None,
        languages: Optional[list[str]] = None,
        domains: Optional[list[str]] = None,
        preferred_workloads: Optional[list[str]] = None,
        historical_accuracy: float = 1.0,
        benchmark_performance: float = 0.0,
        reliability: float = 1.0,
        descriptor: Optional[AgentDescriptor] = None,
    ) -> dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        profile = {
            "skills": sorted({str(item).lower() for item in skills or []}),
            "languages": sorted({str(item).lower() for item in languages or []}),
            "domains": sorted({str(item).lower() for item in domains or []}),
            "preferred_workloads": sorted({str(item).lower() for item in preferred_workloads or []}),
            "historical_accuracy": self._bounded(historical_accuracy),
            "benchmark_performance": self._bounded(benchmark_performance),
            "reliability": self._bounded(reliability),
        }
        with self._lock:
            if descriptor is not None and self.registry.get_agent(agent_id) is None:
                self.registry.register_agent(descriptor)
            self._profiles[agent_id] = profile
            return dict(profile)

    def profile(self, agent_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            profile = self._profiles.get(agent_id)
            return dict(profile) if profile else None

    def discover(
        self,
        skills: Optional[list[str]] = None,
        languages: Optional[list[str]] = None,
        domains: Optional[list[str]] = None,
        available_only: bool = True,
    ) -> list[dict[str, Any]]:
        required = {
            "skills": {str(item).lower() for item in skills or []},
            "languages": {str(item).lower() for item in languages or []},
            "domains": {str(item).lower() for item in domains or []},
        }
        results = []
        with self._lock:
            profiles = dict(self._profiles)
        for descriptor in self.registry.get_all_agents():
            profile = profiles.get(descriptor.agent_id, {})
            if available_only and not descriptor.is_available:
                continue
            if any(not values.issubset(set(profile.get(name, []))) for name, values in required.items()):
                continue
            results.append({"agent": descriptor, "profile": dict(profile)})
        return sorted(results, key=lambda item: item["agent"].agent_id)

    def recommend(
        self,
        skills: Optional[list[str]] = None,
        languages: Optional[list[str]] = None,
        domains: Optional[list[str]] = None,
        available_only: bool = True,
    ) -> Optional[dict[str, Any]]:
        candidates = self.discover(skills, languages, domains, available_only)
        if not candidates:
            return None
        required_count = sum(len(values or []) for values in (skills, languages, domains))
        def score(item: dict[str, Any]) -> tuple[float, str]:
            profile = item["profile"]
            descriptor = item["agent"]
            accuracy = profile.get("historical_accuracy", descriptor.historical_success_rate)
            reliability = profile.get("reliability", descriptor.historical_success_rate)
            benchmark = profile.get("benchmark_performance", 0.0)
            availability = 1.0 - descriptor.workload / max(1, descriptor.max_workload)
            return (
                0.35 * accuracy + 0.30 * reliability + 0.20 * benchmark
                + 0.15 * availability + min(0.05, required_count * 0.01),
                descriptor.agent_id,
            )
        return min(candidates, key=lambda item: (-score(item)[0], item["agent"].agent_id))

    @staticmethod
    def _bounded(value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 4)
