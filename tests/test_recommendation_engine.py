from core.engineering_memory import EngineeringMemory
from core.recommendation_engine import RecommendationEngine


def test_recommendations_are_evidence_backed_and_deduplicated(tmp_path):
    memory = EngineeringMemory(tmp_path)
    memory.store({
        "type": "lesson",
        "title": "Cache lesson",
        "recommendation": "Use a bounded cache",
        "confidence": 0.9,
        "success": True,
    })
    engine = RecommendationEngine(memory)

    results = engine.recommend("cache", limit=3)
    assert len(results) == 1
    assert results[0]["recommendation"] == "Use a bounded cache"
    assert results[0]["source_record_id"]
