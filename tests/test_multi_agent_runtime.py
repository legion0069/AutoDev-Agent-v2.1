from __future__ import annotations

import threading
import time

from core.multi_agent.agent_registry import AgentDescriptor, AgentRole
from core.multi_agent_runtime import MultiAgentRuntime


def test_dispatch_records_only_one_active_workload_decrement() -> None:
    release_slow = threading.Event()
    slow_started = threading.Event()

    def handler(task: dict[str, str]) -> str:
        if task["id"] == "slow":
            slow_started.set()
            release_slow.wait(timeout=2)
        else:
            time.sleep(0.02)
        return task["id"]

    runtime = MultiAgentRuntime(max_workers=2)
    runtime.register_agent(
        AgentDescriptor(
            agent_id="agent",
            name="Agent",
            role=AgentRole.BACKEND_ENGINEER,
            capabilities=["implementation"],
            max_workload=2,
        ),
        handler=handler,
    )
    results: dict[str, dict] = {}
    slow = threading.Thread(
        target=lambda: results.setdefault(
            "slow", runtime.dispatch({"id": "slow"}, ["implementation"])
        )
    )
    fast = threading.Thread(
        target=lambda: results.setdefault(
            "fast", runtime.dispatch({"id": "fast"}, ["implementation"])
        )
    )
    try:
        slow.start()
        assert slow_started.wait(timeout=1)
        fast.start()
        fast.join(timeout=1)
        assert not fast.is_alive()
        assert runtime.get_status("agent")["workload"] == 1
    finally:
        release_slow.set()
        slow.join(timeout=2)
        fast.join(timeout=2)
        runtime.close()
    assert results["fast"]["result"] == "fast"
    assert results["slow"]["result"] == "slow"
    assert runtime.get_status("agent")["workload"] == 0


def test_remove_agent_cleans_its_inbox() -> None:
    runtime = MultiAgentRuntime()
    runtime.register_agent(agent_id="temporary", capabilities=["testing"])
    runtime.bus.publish("STATUS", "orchestrator", "temporary", {"ready": True})

    assert runtime.remove_agent("temporary") is True
    assert runtime.bus.inbox_size("temporary") == 0
    assert runtime.remove_agent("temporary") is False
    runtime.close()


def test_dispatch_can_assign_without_invoking_handler() -> None:
    called = []
    runtime = MultiAgentRuntime()
    runtime.register_agent(
        agent_id="planner",
        capabilities=["planning"],
        handler=lambda task: called.append(task),
    )

    result = runtime.dispatch(
        {"id": "plan"},
        ["planning"],
        execute_handler=False,
    )

    assert result["status"] == "queued"
    assert called == []
    assert runtime.bus.inbox_size("planner") == 1
    runtime.close()


def test_timed_out_handler_remains_busy_until_it_exits() -> None:
    started = threading.Event()
    release = threading.Event()

    def handler(_: dict[str, str]) -> None:
        started.set()
        release.wait(timeout=2)

    runtime = MultiAgentRuntime(max_workers=2)
    runtime.register_agent(
        agent_id="worker",
        capabilities=["testing"],
        max_workload=2,
        handler=handler,
    )
    try:
        try:
            runtime.dispatch(
                {"id": "slow"},
                ["testing"],
                timeout=0.01,
            )
        except TimeoutError:
            pass
        else:
            raise AssertionError("dispatch should time out")
        assert started.is_set()
        assert runtime.get_status("worker")["workload"] == 1
    finally:
        release.set()
        deadline = time.monotonic() + 1
        while runtime.get_status("worker")["workload"] and time.monotonic() < deadline:
            time.sleep(0.01)
        runtime.close()
    assert runtime.get_status("worker")["workload"] == 0
