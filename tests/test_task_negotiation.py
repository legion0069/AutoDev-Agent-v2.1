from core.capability_manager import AgentCapabilityManager
from core.multi_agent.agent_registry import AgentDescriptor, AgentRegistry, AgentRole
from core.task_negotiation import TaskNegotiationEngine


def test_negotiation_uses_capabilities_then_stable_agent_id_tie_break() -> None:
    registry = AgentRegistry()
    manager = AgentCapabilityManager(registry)
    for agent_id in ("z-agent", "a-agent"):
        descriptor = AgentDescriptor(
            agent_id=agent_id,
            name=agent_id,
            role=AgentRole.BACKEND_ENGINEER,
            capabilities=["python", "implementation"],
        )
        registry.register_agent(descriptor)
        manager.register(agent_id, skills=descriptor.capabilities)
    result = TaskNegotiationEngine(manager).negotiate(
        {"title": "Implement endpoint"}, ["implementation"]
    )

    assert result.agent_id == "a-agent"
    assert result.candidates[0]["agent_id"] == "a-agent"
    assert result.reason


def test_negotiation_has_no_assignment_when_capability_is_missing() -> None:
    manager = AgentCapabilityManager()
    result = TaskNegotiationEngine(manager).negotiate({}, ["security"])
    assert result.agent_id is None
    assert result.candidates == ()
