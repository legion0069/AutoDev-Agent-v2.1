from core.capability_manager import AgentCapabilityManager
from core.multi_agent.agent_registry import AgentDescriptor, AgentRegistry, AgentRole


def test_discovery_filters_skills_languages_and_recommends_stably() -> None:
    registry = AgentRegistry()
    manager = AgentCapabilityManager(registry)
    for agent_id in ("beta", "alpha"):
        descriptor = AgentDescriptor(
            agent_id=agent_id,
            name=agent_id,
            role=AgentRole.QA_ENGINEER,
            capabilities=["testing"],
        )
        registry.register_agent(descriptor)
        manager.register(agent_id, skills=["testing"], languages=["python"])

    matches = manager.discover(skills=["testing"], languages=["python"])
    assert [entry["agent"].agent_id for entry in matches] == ["alpha", "beta"]
    assert manager.recommend(skills=["testing"])["agent"].agent_id == "alpha"
    assert manager.discover(languages=["rust"]) == []
