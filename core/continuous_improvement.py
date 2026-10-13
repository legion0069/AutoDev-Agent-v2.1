"""Evidence-ranked roadmap combining all AutoDev improvement signals."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


class ContinuousImprovementEngine:
    """Combines research, architecture, performance, learning, and delivery evidence."""

    SOURCE_KEYS = (
        "research",
        "architecture",
        "performance",
        "learning",
        "reflection",
        "analytics",
        "engineering",
    )

    def generate_roadmap(self, **sources: Mapping[str, Any] | None) -> dict[str, Any]:
        items_by_key: dict[str, dict[str, Any]] = {}
        summaries: dict[str, Any] = {}
        for source_name in self.SOURCE_KEYS:
            source = sources.get(source_name) or {}
            summaries[source_name] = self._source_summary(source)
            recommendations = source.get("recommendations", [])
            if isinstance(source.get("roadmap"), list):
                recommendations = list(recommendations) + source["roadmap"]
            if source_name == "research" and source.get("goal"):
                recommendations = list(recommendations) + [{
                    "title": source["goal"],
                    "priority": source.get("severity", "medium"),
                    "evidence": source.get("evidence", {}),
                }]
            for recommendation in recommendations if isinstance(recommendations, list) else []:
                item = self._normalize(source_name, recommendation)
                if item is None:
                    continue
                key = item["title"].casefold()
                existing = items_by_key.get(key)
                if existing is None:
                    items_by_key[key] = item
                else:
                    existing["sources"] = sorted(set(existing["sources"]) | {source_name})
                    existing["evidence"].extend(item["evidence"])
                    existing["priority_score"] = max(existing["priority_score"], item["priority_score"])

        roadmap = sorted(
            items_by_key.values(),
            key=lambda item: (-item["priority_score"], item["title"].casefold(), item["item_id"]),
        )
        for item in roadmap:
            item["sources"] = sorted(set(item["sources"]))
            item["evidence"] = sorted(item["evidence"], key=lambda value: json.dumps(value, sort_keys=True, default=str))
        return {"roadmap": roadmap, "source_summaries": summaries}

    @staticmethod
    def _source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "recommendation_count": len(source.get("recommendations", []))
            if isinstance(source.get("recommendations", []), list) else 0,
            "available": bool(source),
        }

    @staticmethod
    def _normalize(source: str, value: Any) -> dict[str, Any] | None:
        if isinstance(value, str):
            title = value.strip()
            priority = "medium"
            evidence: Any = {}
        elif isinstance(value, Mapping):
            title = str(value.get("title", value.get("action", ""))).strip()
            priority = str(value.get("priority", "medium")).lower()
            evidence = value.get("evidence", {})
        else:
            return None
        if not title:
            return None
        score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(priority, 2)
        payload = json.dumps([title, source], sort_keys=True, default=str)
        return {
            "item_id": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
            "title": title,
            "priority": priority,
            "priority_score": score,
            "sources": [source],
            "evidence": [evidence] if evidence else [],
            "status": "proposed",
        }
