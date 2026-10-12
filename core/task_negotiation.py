"""Deterministic agent selection across capability, workload, and performance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from core.capability_manager import AgentCapabilityManager
from core.multi_agent.agent_registry import AgentDescriptor


@dataclass(frozen=True)
class NegotiationResult:
    agent_id: Optional[str]
    score: float
    candidates: tuple[dict[str, Any], ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "score": self.score,
            "candidates": [dict(item) for item in self.candidates],
            "reason": self.reason,
        }


class TaskNegotiationEngine:
    """Scores eligible agents with fixed weights and stable identifier tie-breaks."""

    def __init__(
        self,
        capability_manager: AgentCapabilityManager,
        metrics_tracker: Optional[Any] = None,
    ) -> None:
        self.capability_manager = capability_manager
        self.metrics_tracker = metrics_tracker

    def negotiate(
        self,
        task: Any,
        required_capabilities: Optional[list[str]] = None,
        required_languages: Optional[list[str]] = None,
        required_domains: Optional[list[str]] = None,
        estimated_runtime: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> NegotiationResult:
        skills = list(required_capabilities or self._get(task, "required_capabilities", []))
        languages = list(required_languages or self._get(task, "required_languages", []))
        domains = list(required_domains or self._get(task, "required_domains", []))
        candidates = self.capability_manager.discover(
            skills=skills,
            languages=languages,
            domains=domains,
            available_only=True,
        )
        ranked = []
        for candidate in candidates:
            descriptor: AgentDescriptor = candidate["agent"]
            profile = candidate["profile"]
            workload_capacity = max(1, descriptor.max_workload)
            workload_score = max(0.0, 1.0 - descriptor.workload / workload_capacity)
            success = profile.get("historical_accuracy", descriptor.historical_success_rate)
            reliability = profile.get("reliability", descriptor.historical_success_rate)
            runtime_score = 1.0
            if estimated_runtime and estimated_runtime > 0:
                observed = descriptor.average_duration
                runtime_score = 1.0 if observed <= 0 else min(1.0, estimated_runtime / observed)
            confidence_score = self._bounded(
                confidence if confidence is not None else 1.0, 1.0
            )
            required = {item.lower() for item in skills + languages + domains}
            provided = set(profile.get("skills", [])) | set(profile.get("languages", [])) | set(profile.get("domains", []))
            capability_score = len(required & provided) / len(required) if required else 1.0
            metric = self.metrics_tracker.get_metrics(descriptor.agent_id) if self.metrics_tracker else {}
            historical_score = self._bounded(
                metric.get("success_rate", success), 1.0
            )
            score = (
                0.30 * capability_score
                + 0.20 * historical_score
                + 0.15 * workload_score
                + 0.10 * runtime_score
                + 0.10 * confidence_score
                + 0.15 * self._bounded(reliability, 1.0)
            )
            ranked.append({
                "agent_id": descriptor.agent_id,
                "score": round(score, 6),
                "capability_score": round(capability_score, 6),
                "historical_success": round(historical_score, 6),
                "workload_score": round(workload_score, 6),
                "runtime_score": round(runtime_score, 6),
                "confidence": round(confidence_score, 6),
                "available": descriptor.is_available,
            })
        ranked.sort(key=lambda item: (-item["score"], item["agent_id"]))
        if not ranked:
            return NegotiationResult(None, 0.0, (), "No available agent satisfies the requested capabilities.")
        winner = ranked[0]
        return NegotiationResult(
            winner["agent_id"],
            winner["score"],
            tuple(ranked),
            "Selected the highest-scoring available agent; ties use ascending agent ID.",
        )

    @staticmethod
    def _get(task: Any, name: str, default: Any = None) -> Any:
        return task.get(name, default) if isinstance(task, dict) else getattr(task, name, default)

    @staticmethod
    def _bounded(value: Any, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(maximum, number))
