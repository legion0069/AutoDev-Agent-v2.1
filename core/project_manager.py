"""Project, epic, sprint, and release planning with stable identifiers."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from core.enterprise.enterprise_models import (
    Epic,
    ReleaseCandidate,
    ReleaseStage,
    SprintPlan,
    SprintState,
    UserStory,
)


@dataclass
class ManagedProject:
    project_id: str
    name: str
    description: str = ""
    status: str = "ACTIVE"
    epic_ids: list[str] = field(default_factory=list)
    sprint_ids: list[str] = field(default_factory=list)
    release_ids: list[str] = field(default_factory=list)
    backlog: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "epic_ids": list(self.epic_ids),
            "sprint_ids": list(self.sprint_ids),
            "release_ids": list(self.release_ids),
            "backlog": copy.deepcopy(self.backlog),
        }


class ProjectManager:
    """Coordinates projects while reusing the established enterprise data models."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projects: dict[str, ManagedProject] = {}
        self._epics: dict[str, Epic] = {}
        self._sprints: dict[str, SprintPlan] = {}
        self._releases: dict[str, ReleaseCandidate] = {}

    def create_project(
        self,
        name: str,
        description: str = "",
        project_id: Optional[str] = None,
    ) -> ManagedProject:
        if not name.strip():
            raise ValueError("Project name must not be empty.")
        with self._lock:
            resolved_id = project_id or f"PROJECT-{len(self._projects) + 1:04d}"
            if resolved_id in self._projects:
                raise ValueError(f"Project {resolved_id!r} already exists.")
            project = ManagedProject(resolved_id, name, description)
            self._projects[resolved_id] = project
            return copy.deepcopy(project)

    def create_epic(
        self,
        project_id: str,
        title: str,
        description: str = "",
        strategic_theme: str = "Core Platform",
        target_quarter: str = "Q1",
        estimated_roi_multiplier: float = 3.0,
    ) -> Epic:
        with self._lock:
            project = self._require_project(project_id)
            epic_id = f"{project_id}-EPIC-{len(project.epic_ids) + 1:03d}"
            epic = Epic(
                epic_id=epic_id,
                title=title,
                description=description,
                strategic_theme=strategic_theme,
                target_quarter=target_quarter,
                estimated_roi_multiplier=estimated_roi_multiplier,
            )
            self._epics[epic_id] = epic
            project.epic_ids.append(epic_id)
            return copy.deepcopy(epic)

    def create_sprint(
        self,
        project_id: str,
        goal: str,
        candidate_stories: Optional[list[UserStory]] = None,
        capacity_points: int = 40,
        duration_days: int = 14,
    ) -> SprintPlan:
        if capacity_points < 0 or duration_days <= 0:
            raise ValueError("Sprint capacity must be non-negative and duration must be positive.")
        with self._lock:
            project = self._require_project(project_id)
            sprint_number = len(project.sprint_ids) + 1
            sprint_id = f"{project_id}-SPRINT-{sprint_number:03d}"
            stories = copy.deepcopy(candidate_stories or [])
            start_date = (sprint_number - 1) * duration_days * 86400.0
            sprint = SprintPlan(
                sprint_id=sprint_id,
                sprint_number=sprint_number,
                goal=goal,
                start_date=start_date,
                end_date=start_date + duration_days * 86400.0,
                capacity_points=capacity_points,
                committed_points=sum(story.story_points for story in stories),
                stories=stories,
                state=SprintState.PLANNING,
            )
            self._sprints[sprint_id] = sprint
            project.sprint_ids.append(sprint_id)
            return copy.deepcopy(sprint)

    def create_release(
        self,
        project_id: str,
        version: str,
        stage: ReleaseStage = ReleaseStage.RELEASE_CANDIDATE,
        checklist_gates: Optional[dict[str, bool]] = None,
    ) -> ReleaseCandidate:
        with self._lock:
            project = self._require_project(project_id)
            release_id = f"{project_id}-RELEASE-{len(project.release_ids) + 1:03d}"
            resolved_stage = ReleaseStage(stage) if isinstance(stage, str) else stage
            gates = {
                "unit_tests_pass": False,
                "integration_tests_pass": False,
                "security_scan_clean": False,
                "performance_sla_met": False,
                "docs_updated": False,
                "executive_signoff": False,
            }
            if checklist_gates is not None:
                gates.update({str(name): bool(passed) for name, passed in checklist_gates.items()})
            release = ReleaseCandidate(
                release_id=release_id,
                version=version,
                stage=resolved_stage,
                checklist_gates=gates,
                created_at=0.0,
            )
            self._releases[release_id] = release
            project.release_ids.append(release_id)
            return copy.deepcopy(release)

    def add_backlog_item(self, project_id: str, item: dict[str, Any]) -> None:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("Backlog items must be dictionaries with a non-empty id.")
        with self._lock:
            project = self._require_project(project_id)
            if any(existing["id"] == item["id"] for existing in project.backlog):
                raise ValueError(f"Backlog item {item['id']!r} already exists.")
            project.backlog.append(copy.deepcopy(item))

    def update_backlog_status(self, project_id: str, item_id: str, status: str) -> bool:
        if not status:
            raise ValueError("Backlog status must not be empty.")
        with self._lock:
            project = self._require_project(project_id)
            for item in project.backlog:
                if item["id"] == item_id:
                    item["status"] = status
                    return True
            return False

    def project_dashboard(self, project_id: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            projects = (
                [self._require_project(project_id)]
                if project_id is not None
                else [self._projects[key] for key in sorted(self._projects)]
            )
            return {
                "project_count": len(projects),
                "projects": [
                    {
                        **project.to_dict(),
                        "epics": [self._epics[key].to_dict() for key in project.epic_ids],
                        "sprints": [self._sprints[key].to_dict() for key in project.sprint_ids],
                        "releases": [self._releases[key].to_dict() for key in project.release_ids],
                        "completed_backlog_items": sum(
                            1 for item in project.backlog
                            if str(item.get("status", "")).lower() == "completed"
                        ),
                    }
                    for project in projects
                ],
            }

    def get_project(self, project_id: str) -> Optional[ManagedProject]:
        with self._lock:
            project = self._projects.get(project_id)
            return copy.deepcopy(project) if project else None

    def _require_project(self, project_id: str) -> ManagedProject:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise KeyError(f"Project {project_id!r} does not exist.") from exc
