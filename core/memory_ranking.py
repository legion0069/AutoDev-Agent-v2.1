"""Deterministic multi-signal ranking of engineering memories."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class MemoryRankingEngine:
    """Ranks memories by recency, importance, similarity, confidence, and utility."""

    WEIGHTS = {
        "recency": 0.15,
        "importance": 0.20,
        "similarity": 0.25,
        "success_rate": 0.15,
        "confidence": 0.10,
        "utility": 0.15,
    }

    def rank(
        self,
        memories: Iterable[Mapping[str, Any]],
        query: str = "",
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        query_tokens = _tokens(query)
        ranked = []
        for memory in memories:
            item = dict(memory)
            factors = self._factors(item, query_tokens, current)
            score = sum(factors[key] * weight for key, weight in self.WEIGHTS.items())
            item["ranking_score"] = round(score, 6)
            item["ranking_factors"] = factors
            ranked.append(item)
        return sorted(
            ranked,
            key=lambda item: (-item["ranking_score"], str(item.get("record_id", item.get("id", "")))),
        )

    def best_memories(
        self,
        memories: Iterable[Mapping[str, Any]],
        query: str = "",
        *,
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must not be negative.")
        return self.rank(memories, query, now=now)[:limit]

    def _factors(
        self,
        item: Mapping[str, Any],
        query_tokens: set[str],
        current: datetime,
    ) -> dict[str, float]:
        raw_importance = float(item.get("importance", 0.0))
        importance = _clamp(raw_importance / 10.0)
        tokens = _tokens(" ".join(
            str(item.get(key, ""))
            for key in ("title", "content", "summary", "description", "solution", "root_cause")
        ))
        tags = _tokens(" ".join(map(str, item.get("tags", []))))
        overlap = len(query_tokens & (tokens | tags)) / len(query_tokens) if query_tokens else 1.0
        success = item.get("success_rate", item.get("success", 0.5))
        if isinstance(success, bool):
            success = float(success)
        success_rate = _clamp(float(success))
        confidence = _clamp(float(item.get("confidence", 0.5)))
        utility = _clamp(float(item.get("utility", item.get("reuse_count", 0.0) / 10.0)))
        age_days = _age_days(item.get("timestamp", item.get("created_at")), current)
        recency = math.exp(-age_days / 180.0)
        return {
            "recency": round(_clamp(recency), 6),
            "importance": round(importance, 6),
            "similarity": round(_clamp(overlap), 6),
            "success_rate": round(success_rate, 6),
            "confidence": round(confidence, 6),
            "utility": round(utility, 6),
        }


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", value.casefold()) if len(token) > 1}


def _age_days(value: Any, current: datetime) -> float:
    try:
        timestamp = float(value) if isinstance(value, (int, float)) else None
        if timestamp is not None:
            created = datetime.fromtimestamp(timestamp, timezone.utc)
        else:
            created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (current - created).total_seconds() / 86400.0)
    except (ValueError, TypeError, OverflowError, OSError):
        return 180.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value)) if math.isfinite(value) else 0.0
