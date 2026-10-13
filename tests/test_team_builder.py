from core.multi_agent.agent_registry import AgentDescriptor, AgentRole
from core.multi_agent_runtime import MultiAgentRuntime
from core.organization_manager import OrganizationManager
from core.team_builder import TeamBuilder


def test_team_builder_uses_capability_and_stable_reliability_ranking():
    runtime = MultiAgentRuntime()
    runtime.register_agent(AgentDescriptor(
        "backend-b", "Backend B", AgentRole.BACKEND_ENGINEER,
        capabilities=["python", "implementation"], priority=50,
    ))
    runtime.register_agent(AgentDescriptor(
        "backend-a", "Backend A", AgentRole.BACKEND_ENGINEER,
        capabilities=["python", "implementation"], priority=50,
    ))
    manager = OrganizationManager(runtime)

    result = TeamBuilder(manager, runtime).build_team(
        "Payments", technology_stack=["python"], required_roles=["Backend"]
    )

    assert result["role_assignments"] == {"Backend": "backend-a"}
    assert result["team_id"] == "TEAM-0001"
    runtime.close()


def test_recommendations_limit_validation():
    runtime = MultiAgentRuntime()
    runtime.register_agent(AgentDescriptor(
        "qa", "QA", AgentRole.QA_ENGINEER, capabilities=["testing"]
    ))
    builder = TeamBuilder(OrganizationManager(runtime), runtime)
    assert builder.recommend_agents("QA")[0]["agent_id"] == "qa"
    runtime.close()


def test_historical_success_rate_is_used_for_agent_recommendation(tmp_path):
    from core.agent_metrics import AgentMetricsTracker

    runtime = MultiAgentRuntime()
    for agent_id in ("reliable", "new"):
        runtime.register_agent(AgentDescriptor(
            agent_id, agent_id, AgentRole.BACKEND_ENGINEER, capabilities=["python"]
        ))
    metrics = AgentMetricsTracker(tmp_path)
    metrics.record("reliable", success=True)
    metrics.record("reliable", success=True)
    metrics.record("new", success=False)

    builder = TeamBuilder(OrganizationManager(runtime), runtime, metrics)
    assert builder.recommend_agents("Backend")[0]["agent_id"] == "reliable"
    runtime.close()
