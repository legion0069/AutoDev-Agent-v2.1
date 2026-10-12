from core.agent_metrics import AgentMetricsTracker


def test_metrics_persist_and_summarize_deterministically(tmp_path) -> None:
    tracker = AgentMetricsTracker(tmp_path)
    result = tracker.record(
        "worker",
        success=True,
        execution_time=2.0,
        review_score=90,
        defects=0,
        resource_usage={"memory_mb": 12},
    )
    tracker.record("worker", success=False, execution_time=4.0, defects=1)

    restored = AgentMetricsTracker(tmp_path)
    metrics = restored.get_metrics("worker")
    assert metrics["task_count"] == 2
    assert metrics["success_rate"] == 0.5
    assert metrics["average_execution_time"] == 3.0
    assert result["task_count"] == 1
    assert restored.all_metrics()["worker"] == metrics
