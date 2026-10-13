from core.continuous_improvement import ContinuousImprovementEngine


def test_roadmap_merges_duplicate_recommendations_and_orders_by_priority():
    result = ContinuousImprovementEngine().generate_roadmap(
        research={"recommendations": [{
            "title": "Reduce coupling",
            "priority": "high",
            "evidence": {"modules": 3},
        }]},
        architecture={"recommendations": [{
            "title": "reduce coupling",
            "priority": "medium",
            "evidence": {"cycles": 1},
        }]},
        performance={"recommendations": ["Profile slow execution"]},
    )

    assert len(result["roadmap"]) == 2
    merged = next(item for item in result["roadmap"] if item["title"] == "Reduce coupling")
    assert merged["priority"] == "high"
    assert merged["sources"] == ["architecture", "research"]
    assert len(merged["evidence"]) == 2
    assert result["roadmap"][0]["priority"] == "high"
