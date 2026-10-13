from core.adaptive_planner import AdaptivePlanner
from core.delivery_manager import DeliveryManager
from core.engineering_analytics import EngineeringAnalytics
from core.engineering_manager import EngineeringManager
from core.executive_dashboard import ExecutiveDashboard
from core.organization_manager import OrganizationManager
from core.project_manager import ProjectManager
from core.risk_manager import RiskManager
from core.team_builder import TeamBuilder
from agents.task_planner_agent import Task
from core.orchestrator import Orchestrator


def test_organization_project_delivery_and_dashboard_workflow(tmp_path):
    organization = OrganizationManager()
    project_manager = ProjectManager()
    team_builder = TeamBuilder(organization)
    project = project_manager.create_project("Migration")
    team = team_builder.build_team("Migration", required_roles=["Backend"])
    project_manager.create_epic(project.project_id, "Core migration")
    ordered = AdaptivePlanner().order_backlog([
        {"id": "implementation", "dependencies": ["design"], "priority": 2},
        {"id": "design", "priority": 1},
    ])
    assert [task["id"] for task in ordered] == ["design", "implementation"]

    risks = RiskManager().analyze({"technical_debt_items": 1}).to_dict()
    readiness = DeliveryManager().assess_release(
        "REL-1",
        {gate: True for gate in DeliveryManager.REQUIRED_GATES},
        risks,
    )
    analytics = EngineeringAnalytics(tmp_path)
    analytics.record(completed=True, deployments=1)
    engineering = EngineeringManager()
    engineering.record_task("T-1", "completed", team_id=team["team_id"], quality_score=92)
    dashboard = ExecutiveDashboard().build(
        organization=organization.organization_summary(),
        projects=project_manager.project_dashboard(),
        risks=risks,
        performance=analytics.metrics(),
    )

    assert readiness["ready"] is False
    assert dashboard["organization"]["team_count"] == 1
    assert dashboard["projects"]["project_count"] == 1
    assert engineering.generate_report()["completed_tasks"] == 1


def test_orchestrator_organization_mode_is_opt_in_and_dependency_safe(tmp_path):
    root = tmp_path / "workspace"
    legacy = Orchestrator(project_root=root / "legacy")
    assert legacy.organization_mode is False
    assert legacy.project_manager is None

    orchestrator = Orchestrator(
        project_root=root / "organization",
        plan_path=tmp_path / "plan.json",
        state_path=tmp_path / "state.json",
        tasks_path=tmp_path / "tasks.json",
        log_dir=tmp_path / "logs",
        organization_mode=True,
    )
    try:
        tasks = [
            Task(id="implement", title="Implement", description="Implementation", priority=2, dependencies=["design"]),
            Task(id="design", title="Design", description="Architecture", priority=1),
        ]
        context = {"project_name": "Opt-in project", "technology_stack": ["python"]}
        ordered = orchestrator._prepare_organization_cycle(tasks, set(), context)
        orchestrator._update_organization_dashboard(True, 92.0)

        assert [task.id for task in ordered] == ["design", "implement"]
        assert context["organization_context"]["project_id"] == "CURRENT-PROJECT"
        assert orchestrator.latest_organization_dashboard["projects"]["project_count"] == 1
        assert orchestrator.latest_organization_dashboard["organization"]["team_count"] == 1
        assert len(orchestrator.latest_organization_dashboard["releases"]) == 1
    finally:
        if orchestrator.multi_agent_runtime is not None:
            orchestrator.multi_agent_runtime.close()
