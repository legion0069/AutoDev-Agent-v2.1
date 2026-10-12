from core.agent_metrics import AgentMetricsTracker
from core.multi_agent_runtime import MultiAgentRuntime
from core.orchestrator import Orchestrator


def test_orchestrator_publishes_structured_learning_and_metrics(tmp_path) -> None:
    runtime = MultiAgentRuntime()
    runtime.register_agent(agent_id="worker", capabilities=["implementation"])
    metrics = AgentMetricsTracker(tmp_path / "agent-metrics")
    orchestrator = Orchestrator(
        project_root=tmp_path,
        multi_agent_runtime=runtime,
        agent_metrics_tracker=metrics,
    )

    orchestrator._publish_multi_agent_outcome(
        task_id="feature-1",
        assignment={"agent_id": "worker", "message_id": "request-1"},
        success=True,
        execution_time=1.5,
        review_score=92.0,
        retry_count=0,
        learning_summary={
            "title": "Add deterministic routing",
            "description": "Route task messages with stable priorities",
            "files_affected": ["core/agent_bus.py"],
            "test_pass_rate": 100.0,
        },
    )

    assert orchestrator.knowledge_reasoner.sources[-1]["task_id"] == "feature-1"
    assert orchestrator.knowledge_reasoner.reason("deterministic routing")["findings"]
    assert metrics.get_metrics("worker")["success_rate"] == 1.0
    assert runtime.bus.history()[-1].message_type.value == "LEARNING_EVENT"
    runtime.close()
