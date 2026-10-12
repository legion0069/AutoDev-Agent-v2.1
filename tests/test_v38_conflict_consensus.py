from core.conflict_resolution import ConflictResolutionEngine, ConflictKind
from core.consensus_engine import ConsensusEngine


def test_conflict_resolution_is_deterministic() -> None:
    engine = ConflictResolutionEngine(policy="highest_priority")
    conflicts = engine.detect_conflicts(
        tasks=[
            {"id": "one", "agent_id": "z-agent", "files": ["src/a.py"]},
            {"id": "two", "agent_id": "a-agent", "files": ["src/a.py"]},
        ]
    )
    ownership = next(item for item in conflicts if item.kind == ConflictKind.FILE_OWNERSHIP)

    result = engine.resolve(ownership, priorities={"z-agent": 5, "a-agent": 5})
    assert result.winner == "a-agent"
    assert result.resolved


def test_consensus_decision_explains_votes() -> None:
    engine = ConsensusEngine()
    votes = [
        {"reviewer_id": "architect", "decision": "approve", "confidence_score": 0.9},
        {"reviewer_id": "tester", "decision": "approve", "confidence_score": 0.8},
        {"reviewer_id": "reviewer", "decision": "reject", "confidence_score": 0.7},
    ]
    result = engine.decide(votes, strategy="majority")
    repeated = engine.decide(votes, strategy="majority")
    assert result.approved
    assert result.approval_count == 2
    assert result.vote_count == 3
    assert "majority" in result.reason.lower()
    assert repeated == result
