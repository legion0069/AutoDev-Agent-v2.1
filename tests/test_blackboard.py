import pytest

from core.blackboard import Blackboard, BlackboardConflictError


def test_version_history_copy_isolation_and_rollback() -> None:
    board = Blackboard()
    value = {"items": [1]}
    assert board.write("plan", value, writer="planner") == 1
    value["items"].append(2)
    assert board.read("plan") == {"items": [1]}
    assert board.write("plan", {"items": [3]}, writer="reviewer", expected_version=1) == 2
    assert board.rollback("plan", writer="planner") == 3
    assert board.read("plan") == {"items": [1]}
    assert board.snapshot()["versions"]["plan"] == 3


def test_lock_and_optimistic_conflicts() -> None:
    board = Blackboard()
    assert board.lock("decision", "architect")
    with pytest.raises(BlackboardConflictError):
        board.write("decision", "A", writer="reviewer")
    assert board.write("decision", "A", writer="architect", expected_version=0) == 1
    assert not board.unlock("decision", "reviewer")
    assert board.unlock("decision", "architect")
    with pytest.raises(BlackboardConflictError):
        board.write("decision", "B", expected_version=0)
