"""Deterministic schedule, architecture, dependency, resource, and quality risk analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RiskAssessment:
    risks: list[dict[str, Any]] = field(default_factory=list)
    mitigation_plan: list[dict[str, str]] = field(default_factory=list)

    @property
    def risk_count(self) -> int:
        return len(self.risks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_count": self.risk_count,
            "risks": list(self.risks),
            "mitigation_plan": list(self.mitigation_plan),
        }


class RiskManager:
    """Turns explicit project signals into sorted risks and practical mitigations."""

    def analyze(
        self,
        signals: Optional[dict[str, Any]] = None,
        resource_manager: Optional[Any] = None,
    ) -> RiskAssessment:
        values = dict(signals or {})
        risks: list[dict[str, Any]] = []
        self._add(risks, "schedule", int(values.get("overdue_milestones", 0)) > 0 or float(values.get("schedule_variance", 0)) > 0,
                  "HIGH", "Milestones are overdue or behind schedule.")
        self._add(risks, "architecture", float(values.get("architecture_risk_score", 0)) >= 70,
                  "HIGH", "Architecture risk score exceeds the review threshold.")
        self._add(risks, "technical_debt", int(values.get("technical_debt_items", 0)) > 0,
                  "MEDIUM", "Technical debt items are accumulating.")
        self._add(risks, "dependency", int(values.get("dependency_bottlenecks", 0)) > 0,
                  "HIGH", "Dependency bottlenecks may block the critical path.")
        self._add(risks, "quality", float(values.get("quality_score", 100)) < 80 or float(values.get("quality_trend", 0)) < 0,
                  "HIGH", "Quality is below target or trending downward.")
        if resource_manager is not None:
            demand = values.get("resource_demand", {})
            forecast = resource_manager.forecast(demand)
            for resource, estimate in forecast.items():
                if estimate["sufficient"] is False:
                    risks.append({
                        "category": "resource",
                        "severity": "HIGH",
                        "description": f"Insufficient {resource} capacity for planned demand.",
                        "resource": resource,
                    })
        risks.sort(key=lambda item: ({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}[item["severity"]], item["category"]))
        mitigation = [
            {
                "risk": item["category"],
                "action": self._mitigation(item["category"]),
            }
            for item in risks
        ]
        return RiskAssessment(risks=risks, mitigation_plan=mitigation)

    @staticmethod
    def _add(risks: list[dict[str, Any]], category: str, present: bool, severity: str, description: str) -> None:
        if present:
            risks.append({"category": category, "severity": severity, "description": description})

    @staticmethod
    def _mitigation(category: str) -> str:
        actions = {
            "schedule": "Re-sequence milestones and protect critical-path capacity.",
            "architecture": "Schedule an architecture review and document the accepted decision.",
            "technical_debt": "Prioritize debt items with the affected delivery work.",
            "dependency": "Resolve or isolate the blocking dependency before downstream work.",
            "quality": "Add focused validation and review the quality regression before release.",
            "resource": "Rebalance queued allocations or reduce concurrent demand.",
        }
        return actions[category]
