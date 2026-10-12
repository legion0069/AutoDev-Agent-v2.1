from core.multi_agent_runtime import MultiAgentRuntime
from core.orchestrator import Orchestrator


def test_multi_agent_runtime_is_opt_in(tmp_path) -> None:
    legacy = Orchestrator(project_root=tmp_path)
    assert legacy.coordination_mode == "single"
    assert legacy.multi_agent_runtime is None

    collaborative = Orchestrator(project_root=tmp_path, coordination_mode="multi_agent")
    assert collaborative.multi_agent_runtime is not None
    assert collaborative.multi_agent_collaboration is not None
    assert {
        agent.agent_id for agent in collaborative.multi_agent_runtime.discover(available_only=False)
    } == {
        "autodev_backend",
        "autodev_testing",
        "autodev_security",
        "autodev_documentation",
    }
    collaborative.multi_agent_runtime.close()


def test_injected_runtime_preserves_single_mode_legacy_default(tmp_path) -> None:
    runtime = MultiAgentRuntime()
    orchestrator = Orchestrator(project_root=tmp_path, multi_agent_runtime=runtime)
    assert orchestrator.coordination_mode == "single"
    assert orchestrator.multi_agent_runtime is runtime
    runtime.close()
