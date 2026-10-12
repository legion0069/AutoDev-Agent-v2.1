from __future__ import annotations

import json

from core.decision_engine import DecisionEngine
from core.explainability import ExplainabilityEngine
from core.hypothesis_engine import HypothesisEngine, HypothesisStatus
from core.knowledge_reasoner import KnowledgeReasoner
from core.learning.learning_coordinator import SelfEvolvingEngine
from core.learning.learning_engine import LearningEngine
from core.learning.reflection_engine import ReflectionEngine
from core.planning_revision import PlanningRevisionEngine
from core.reasoning_engine import ReasoningEngine
from core.reasoning_cache import ReasoningCache
from benchmark_v37_reasoning import run_benchmarks


def test_reasoning_is_repeatable_cached_and_excludes_private_context(tmp_path):
    engine = ReasoningEngine(project_root=tmp_path)
    context = {
        "files": ["src/b.py", "src/a.py"],
        "constraints": ["stdlib only"],
        "chain_of_thought": "must never appear in public results",
    }

    first = engine.reason("Improve cache reliability. Add deterministic invalidation.", context)
    second = engine.reason("Improve cache reliability. Add deterministic invalidation.", context)

    assert first == second
    assert first["steps"] == [
        "Improve cache reliability",
        "Add deterministic invalidation",
    ]
    assert first["constraints"] == ["stdlib only"]
    assert "chain_of_thought" not in json.dumps(first)
    assert engine.statistics()["hits"] == 1

    restored = ReasoningEngine(project_root=tmp_path)
    assert restored.reason("Improve cache reliability. Add deterministic invalidation.", context) == first


def test_reasoning_cache_repairs_corruption_and_versions_entries(tmp_path):
    cache = ReasoningCache("unit", cache_root=tmp_path)
    key = {"x": {3, 1}}
    cache.set(key, {"answer": 42})
    assert cache.get(key) == {"answer": 42}
    entry = next((tmp_path / "unit").glob("*.json"))
    entry.write_text('{"version": 999, "value": {}}', encoding="utf-8")
    assert cache.get(key) is None
    assert cache.statistics()["repairs"] == 1
    assert not entry.exists()


def test_decision_strategy_ranking_is_stable_and_preserves_legacy_proposals(tmp_path):
    engine = DecisionEngine(project_root=str(tmp_path))
    ranked = engine.rank_options([
        {"name": "minimal", "benefit": 0.6, "risk": 0.1, "maintainability": 0.8},
        {"name": "risky", "benefit": 0.9, "risk": 0.9, "maintainability": 0.4},
    ])
    assert ranked[0]["name"] == "minimal"
    assert engine.rank_options([
        {"name": "minimal", "benefit": 0.6, "risk": 0.1, "maintainability": 0.8},
        {"name": "risky", "benefit": 0.9, "risk": 0.9, "maintainability": 0.4},
    ]) == ranked
    proposal_id = engine.create_proposal(
        "Architecture selection", "ARCHITECTURE_CHOICE", ["A", "B"], "tester"
    )
    assert proposal_id.startswith("DEC-")


def test_issue_hypotheses_are_deterministic_and_legacy_formulation_still_works(tmp_path):
    engine = HypothesisEngine(project_root=tmp_path)
    first = engine.generate("stale cache causes incorrect result", limit=3)
    second = engine.generate("stale cache causes incorrect result", limit=3)
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert first[0].hypothesis_id.startswith("HYP-ISSUE-")

    validated = engine.validate(first[0], "reproduction confirmed", supported=True)
    assert validated is not None
    assert validated.status is HypothesisStatus.VALIDATED
    legacy = engine.formulate("A separate legacy hypothesis")
    assert legacy.hypothesis_id.startswith("HYP-")


def test_planning_revision_repairs_cycles_without_mutating_input():
    source = {
        "tasks": [
            {"id": "a", "title": "A", "dependencies": ["b", "missing"]},
            {"id": "b", "title": "B", "dependencies": ["a"]},
        ]
    }
    engine = PlanningRevisionEngine()
    assert any(issue["type"] == "dependency_cycle" for issue in engine.review(source).issues)

    repaired = engine.repair(source)

    assert source["tasks"][0]["dependencies"] == ["b", "missing"]
    assert all(
        dependency in {"a", "b"}
        for task in repaired["tasks"]
        for dependency in task["dependencies"]
    )
    assert not any(issue["type"] == "dependency_cycle" for issue in engine.review(repaired).issues)


def test_planning_revision_parallelizes_only_independent_nonconflicting_tasks():
    plan = [
        {"id": "a", "dependencies": [], "resources": ["a.py"]},
        {"id": "b", "dependencies": [], "resources": ["b.py"]},
        {"id": "c", "dependencies": ["a"], "resources": ["c.py"]},
        {"id": "d", "dependencies": [], "resources": ["b.py"]},
    ]

    revision = PlanningRevisionEngine().optimize(plan)

    assert revision.parallel_groups == [["a", "b"], ["c", "d"]]
    assert revision.review.resource_conflicts == [
        {"task_a": "b", "task_b": "d", "resources": ["b.py"]}
    ]


def test_knowledge_reasoner_ranks_evidence_and_filters_private_trace(tmp_path):
    reasoner = KnowledgeReasoner(
        sources=[
            {"id": "cache-fix", "summary": "Fixed stale cache invalidation behavior."},
            {"id": "parser-fix", "summary": "Improved parser error handling."},
            {
                "id": "private",
                "summary": "Stale cache guidance.",
                "chain_of_thought": "private text",
            },
        ],
        project_root=tmp_path,
    )
    result = reasoner.reason("stale cache invalidation")
    assert result["findings"][0]["source"] == "cache-fix"
    assert "private text" not in json.dumps(result)
    assert reasoner.reason("stale cache invalidation") == result


def test_explainability_returns_safe_public_decision_and_plan_summaries():
    engine = ExplainabilityEngine()
    decision = engine.explain_decision({
        "winner": "safe",
        "confidence": 0.8,
        "evidence": ["tests pass"],
        "chain_of_thought": "private",
    })
    plan = engine.explain_plan([
        {"id": "b", "title": "B", "dependencies": ["a"]},
        {"id": "a", "title": "A"},
    ])
    assert decision["selected_option"] == "safe"
    assert plan["tasks"][0]["id"] == "a"
    assert "private" not in json.dumps((decision, plan))


def test_task_completion_persists_structured_reflection(tmp_path):
    learning = LearningEngine(storage_dir=str(tmp_path / "learning"), auto_persist=False)
    reflection = ReflectionEngine(storage_dir=str(tmp_path / "learning"), auto_persist=False)
    engine = SelfEvolvingEngine(
        storage_dir=str(tmp_path / "learning"),
        learning_engine=learning,
        reflection_engine=reflection,
    )

    result = engine.on_task_completed(
        task_id="T-1",
        task_title="Add focused tests",
        success=True,
        quality_score=92,
        test_pass_rate=80,
        files_affected=["tests/test_reasoning_engine_v37.py"],
        execution_time=1.2,
    )

    structured = result["structured_reflection"]
    assert structured["dimensions"]["output_quality"] == 0.92
    assert "test_coverage" in structured["improvement_priorities"]
    stored = learning.query_knowledge(domain="task_reflection")
    assert len(stored) == 1
    assert json.loads(stored[0].details) == structured


def test_benchmark_runner_writes_warm_cache_measurements(tmp_path):
    result = run_benchmarks(tmp_path, iterations=10)

    assert result["summary"]["warm_cache_hit_ratio"] > 0.9
    assert (tmp_path / "v37_reasoning_benchmark_results.json").is_file()
    assert (tmp_path / "v37_benchmark_history.json").is_file()
    report = json.loads((tmp_path / "performance_report.json").read_text(encoding="utf-8"))
    assert "v37_reasoning_benchmarks" in report
