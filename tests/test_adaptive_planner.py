import pytest

from core.adaptive_planner import AdaptivePlanner


def test_backlog_order_is_priority_aware_and_dependency_safe():
    tasks = [
        {"id": "later", "priority": 2, "dependencies": ["first"]},
        {"id": "low", "priority": 3},
        {"id": "first", "priority": 1},
    ]
    result = AdaptivePlanner().order_backlog(tasks)
    assert [task["id"] for task in result] == ["first", "later", "low"]


def test_planner_rejects_duplicate_and_cyclic_tasks():
    planner = AdaptivePlanner()
    with pytest.raises(ValueError, match="unique"):
        planner.order_backlog([{"id": "x"}, {"id": "x"}])
    with pytest.raises(ValueError, match="cycle"):
        planner.order_backlog([
            {"id": "x", "dependencies": ["y"]},
            {"id": "y", "dependencies": ["x"]},
        ])
