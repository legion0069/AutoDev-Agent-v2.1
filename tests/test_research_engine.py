import json

from core.research_engine import ResearchEngine


def test_research_workflow_is_deterministic_and_persists_findings(tmp_path):
    engine = ResearchEngine(tmp_path)
    observations = {
        "problems": [
            {"title": "Slow planning", "severity": "high", "evidence": {"seconds": 2}}
        ]
    }

    problem = engine.discover_problem(observations)
    assert problem is not None
    assert problem == engine.discover_problem(observations)
    plan = engine.generate_research_plan(problem, ["baseline", "candidate"])
    result = engine.evaluate_results(
        plan,
        {"baseline": [1, 1, 1], "candidate": [2, 2, 2]},
    )
    assert "candidate" in result["comparisons"]
    finding = engine.publish_findings({**plan, "evaluation": result, "title": problem["title"]})
    assert finding["finding_id"]
    assert json.loads((tmp_path / "research_findings.json").read_text()) == [finding]
    reloaded = ResearchEngine(tmp_path)
    second = reloaded.publish_findings({"title": "Another finding"})
    assert {item["finding_id"] for item in reloaded.findings} == {
        finding["finding_id"],
        second["finding_id"],
    }
