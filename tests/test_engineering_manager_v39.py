import pytest

from core.engineering_manager import EngineeringManager


def test_engineering_report_summarizes_delivery_and_quality():
    manager = EngineeringManager()
    manager.record_task("T-1", "completed", team_id="TEAM-1", quality_score=90, review_duration_seconds=2)
    manager.record_task("T-2", "blocked", team_id="TEAM-1", quality_score=70, review_duration_seconds=4)

    report = manager.generate_report(team_statuses=[{"team_id": "TEAM-1"}])
    assert report["completed_tasks"] == 1
    assert report["blocked_tasks"] == 1
    assert report["productivity"] == 0.5
    assert report["average_quality"] == 80
    assert report["review_bottleneck_seconds"] == 6


def test_task_history_is_sorted_and_copied():
    manager = EngineeringManager()
    manager.record_task("B", "active")
    manager.record_task("A", "done")
    history = manager.task_history()
    assert [item["task_id"] for item in history] == ["A", "B"]
    history[0]["status"] = "corrupt"
    assert manager.task_history()[0]["status"] == "DONE"
    with pytest.raises(ValueError):
        manager.record_task("bad", "blocked", review_duration_seconds=-1)
