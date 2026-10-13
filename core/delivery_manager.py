"""Release readiness tracking for project tests, documentation, quality, and sign-off."""

from __future__ import annotations

from typing import Any, Optional


class DeliveryManager:
    """Assesses release gates without treating unknown checks as successful."""

    REQUIRED_GATES = (
        "tests_complete",
        "documentation_ready",
        "security_reviewed",
        "quality_approved",
        "deployment_ready",
    )

    def assess_release(
        self,
        release_id: str,
        checks: Optional[dict[str, bool]] = None,
        risks: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not release_id:
            raise ValueError("Release ID must not be empty.")
        gate_values = {gate: bool((checks or {}).get(gate, False)) for gate in self.REQUIRED_GATES}
        unresolved_risks = int((risks or {}).get("risk_count", 0))
        blockers = [gate for gate, passed in gate_values.items() if not passed]
        if unresolved_risks:
            blockers.append("unresolved_risks")
        passed_count = sum(gate_values.values())
        confidence = passed_count / len(self.REQUIRED_GATES)
        if unresolved_risks:
            confidence *= max(0.0, 1.0 - min(unresolved_risks, 5) * 0.1)
        return {
            "release_id": release_id,
            "ready": not blockers,
            "confidence": round(confidence, 4),
            "gates": gate_values,
            "blockers": blockers,
        }

    def release_readiness(self, release_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.assess_release(release_id, **kwargs)
