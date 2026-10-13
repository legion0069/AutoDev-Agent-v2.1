from datetime import datetime, timezone

from core.memory_ranking import MemoryRankingEngine


def test_ranking_orders_relevant_recent_important_memories():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    memories = [
        {"record_id": "low", "title": "Other topic", "importance": 1, "timestamp": "2024-01-01T00:00:00+00:00"},
        {"record_id": "high", "title": "Cache optimization", "importance": 10, "timestamp": "2024-12-31T00:00:00+00:00"},
    ]

    ranked = MemoryRankingEngine().rank(memories, "cache", now=now)
    assert ranked[0]["record_id"] == "high"
    assert 0 <= ranked[0]["ranking_score"] <= 1
