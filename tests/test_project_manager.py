import pytest

from core.enterprise.enterprise_models import SprintState
from core.project_manager import ProjectManager


def test_project_epic_sprint_release_lifecycle():
    manager = ProjectManager()
    project = manager.create_project("Payment Platform")
    epic = manager.create_epic(project.project_id, "Checkout", "Payment flow")
    sprint = manager.create_sprint(project.project_id, "Deliver checkout", capacity_points=12)
    release = manager.create_release(project.project_id, "1.0.0")

    dashboard = manager.project_dashboard(project.project_id)["projects"][0]
    assert dashboard["epics"][0]["epic_id"] == epic.epic_id
    assert dashboard["sprints"][0]["state"] == SprintState.PLANNING.value
    assert sprint.committed_points == 0
    assert release.created_at == 0.0
    assert not any(release.checklist_gates.values())
    custom_release = manager.create_release(
        project.project_id, "1.0.1", checklist_gates={"unit_tests_pass": True}
    )
    assert custom_release.checklist_gates["unit_tests_pass"] is True
    assert custom_release.checklist_gates["docs_updated"] is False


def test_backlog_validation_and_dashboard_order():
    manager = ProjectManager()
    first = manager.create_project("A")
    second = manager.create_project("B")
    manager.add_backlog_item(first.project_id, {"id": "T-1", "status": "completed"})
    assert manager.project_dashboard()["projects"][0]["project_id"] == first.project_id
    assert manager.project_dashboard(first.project_id)["projects"][0]["completed_backlog_items"] == 1
    with pytest.raises(ValueError):
        manager.add_backlog_item(first.project_id, {"id": "T-1"})
    with pytest.raises(ValueError):
        manager.create_sprint(second.project_id, "bad", capacity_points=-1)
    with pytest.raises(KeyError):
        manager.create_epic("missing", "bad")
