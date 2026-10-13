import pytest

from core.organization_manager import OrganizationManager


def test_team_hierarchy_and_lifecycle():
    manager = OrganizationManager()
    parent = manager.create_team("Platform", ["python"])
    child = manager.create_team("Quality", parent_team_id=parent.team_id)

    assert manager.team_status(parent.team_id)["team_id"] == parent.team_id
    assert manager.organization_summary()["team_count"] == 2
    with pytest.raises(ValueError, match="child teams"):
        manager.remove_team(parent.team_id)
    assert manager.remove_team(parent.team_id, cascade=True)
    assert manager.team_status(child.team_id) is None


def test_agent_assignment_and_role_removal():
    manager = OrganizationManager()
    team = manager.create_team("Backend")
    manager.assign_agent(team.team_id, "agent-1", "Backend")

    assert manager.team_status(team.team_id)["role_assignments"] == {"Backend": "agent-1"}
    assert manager.remove_agent(team.team_id, "agent-1")
    assert manager.team_status(team.team_id)["agent_ids"] == []


def test_parent_must_exist_and_names_must_be_valid():
    manager = OrganizationManager()
    with pytest.raises(KeyError):
        manager.create_team("Orphan", parent_team_id="missing")
    with pytest.raises(ValueError):
        manager.create_team(" ")
