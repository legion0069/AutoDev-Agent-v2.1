import threading

from core.collaboration_engine import CollaborationEngine
from core.multi_agent_runtime import MultiAgentRuntime


def test_plan_and_completion_notifications_update_progress() -> None:
    runtime = MultiAgentRuntime()
    engine = CollaborationEngine(runtime=runtime)
    plan = engine.plan(
        [
            {"id": "setup", "title": "Setup", "dependencies": []},
            {"id": "feature", "title": "Feature", "dependencies": ["setup"]},
        ]
    )
    engine.notify_completion("setup", {"ok": True})

    assert plan["parallel_groups"] == [["setup"], ["feature"]]
    assert engine.progress()["setup"] == {
        "status": "completed",
        "result": {"ok": True},
    }
    assert runtime.bus.history()[-1].payload["task_id"] == "setup"
    runtime.close()


def test_string_resource_is_one_resource_key() -> None:
    engine = CollaborationEngine()
    started = threading.Barrier(2)

    def wait_for_other_task(_: object) -> None:
        started.wait(timeout=1)

    results = engine.execute(
        [
            {
                "id": "first",
                "resources": "alpha",
                "function": wait_for_other_task,
            },
            {
                "id": "second",
                "resources": "beta",
                "function": wait_for_other_task,
            },
        ],
        max_workers=2,
    )

    assert list(results) == ["first", "second"]
