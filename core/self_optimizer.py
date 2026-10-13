"""Recommendation-only self-optimization across AutoDev engineering domains."""

from __future__ import annotations

from typing import Any, Mapping


class SelfOptimizer:
    """Produces measured optimization proposals without changing runtime behavior."""

    DOMAINS = (
        "planning",
        "scheduling",
        "prompting",
        "reasoning",
        "collaboration",
        "learning",
        "execution",
        "caching",
    )

    def optimize(
        self,
        metrics: Mapping[str, Any] | None = None,
        *,
        recommendations: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = dict(metrics or {})
        supplied = recommendations or {}
        proposals = []
        for domain in self.DOMAINS:
            value = data.get(domain, {})
            if isinstance(value, Mapping):
                latency = value.get("latency_seconds", value.get("latency"))
                error_rate = value.get("error_rate", 0.0)
                hit_ratio = value.get("hit_ratio")
            else:
                latency = value if isinstance(value, (int, float)) else None
                error_rate = 0.0
                hit_ratio = None

            actions = supplied.get(domain, [])
            if isinstance(actions, str):
                actions = [actions]
            if actions:
                rationale = "; ".join(sorted(str(action) for action in actions))
            elif domain == "caching" and isinstance(hit_ratio, (int, float)) and hit_ratio < 0.5:
                rationale = "Review cache keys and invalidation boundaries to improve the observed hit ratio."
            elif isinstance(error_rate, (int, float)) and error_rate > 0:
                rationale = "Reduce the observed failure rate with targeted validation and recovery tests."
            elif isinstance(latency, (int, float)) and latency > 1.0:
                rationale = f"Profile the {domain} path and remove measured latency bottlenecks."
            else:
                rationale = "Collect stage-specific telemetry before proposing a behavior-preserving change."
            proposals.append({
                "domain": domain,
                "action": rationale,
                "evidence": {
                    key: data[domain].get(key)
                    for key in ("latency_seconds", "latency", "error_rate", "hit_ratio")
                    if isinstance(data.get(domain), Mapping) and key in data[domain]
                },
                "changes_external_behavior": False,
                "requires_experiment": True,
            })
        return {"proposals": proposals, "behavior_changed": False}
