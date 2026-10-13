"""Organization and team lifecycle management for the opt-in v3.9 workflow."""

from __future__ import annotations

import copy
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class EngineeringTeam:
    team_id: str
    name: str
    capabilities: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    role_assignments: dict[str, str] = field(default_factory=dict)
    parent_team_id: Optional[str] = None
    status: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrganizationManager:
    """Maintains a deterministic team hierarchy around the existing agent runtime."""

    def __init__(self, runtime: Optional[Any] = None) -> None:
        self.runtime = runtime
        self._lock = threading.RLock()
        self._teams: dict[str, EngineeringTeam] = {}
        self._next_team_number = 1

    def create_team(
        self,
        name: str,
        capabilities: Optional[list[str]] = None,
        parent_team_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> EngineeringTeam:
        if not name.strip():
            raise ValueError("Team name must not be empty.")
        with self._lock:
            if parent_team_id is not None and parent_team_id not in self._teams:
                raise KeyError(f"Parent team {parent_team_id!r} does not exist.")
            resolved_id = team_id or f"TEAM-{self._next_team_number:04d}"
            if resolved_id in self._teams:
                raise ValueError(f"Team {resolved_id!r} already exists.")
            team = EngineeringTeam(
                team_id=resolved_id,
                name=name,
                capabilities=sorted(set(capabilities or [])),
                parent_team_id=parent_team_id,
            )
            self._teams[resolved_id] = team
            self._next_team_number += 1
            return copy.deepcopy(team)

    def remove_team(self, team_id: str, cascade: bool = False) -> bool:
        with self._lock:
            if team_id not in self._teams:
                return False
            children = sorted(
                team.team_id for team in self._teams.values()
                if team.parent_team_id == team_id
            )
            if children and not cascade:
                raise ValueError(f"Team {team_id!r} has child teams.")
            for child_id in children:
                self.remove_team(child_id, cascade=True)
            del self._teams[team_id]
            return True

    def assign_agent(
        self,
        team_id: str,
        agent_id: str,
        role: Optional[str] = None,
    ) -> bool:
        if not agent_id:
            raise ValueError("Agent ID must not be empty.")
        with self._lock:
            team = self._require_team(team_id)
            if self.runtime is not None and self.runtime.get_status(agent_id) is None:
                raise KeyError(f"Agent {agent_id!r} is not registered.")
            if agent_id not in team.agent_ids:
                team.agent_ids.append(agent_id)
                team.agent_ids.sort()
            if role:
                team.role_assignments[role] = agent_id
            return True

    def remove_agent(self, team_id: str, agent_id: str) -> bool:
        with self._lock:
            team = self._teams.get(team_id)
            if team is None or agent_id not in team.agent_ids:
                return False
            team.agent_ids.remove(agent_id)
            team.role_assignments = {
                role: assigned
                for role, assigned in team.role_assignments.items()
                if assigned != agent_id
            }
            return True

    def team_status(self, team_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            team = self._teams.get(team_id)
            if team is None:
                return None
            result = team.to_dict()
            statuses = [
                self.runtime.get_status(agent_id)
                for agent_id in team.agent_ids
            ] if self.runtime is not None else []
            statuses = [status for status in statuses if isinstance(status, dict)]
            available = sum(
                1 for status in statuses
                if status.get("status") not in {"OFFLINE", "FAILED"}
                and status.get("workload", 0) < status.get("max_workload", 1)
            )
            result["health"] = round(available / len(statuses), 4) if statuses else 1.0
            result["agent_statuses"] = statuses
            return result

    def organization_summary(self) -> dict[str, Any]:
        with self._lock:
            teams = [self.team_status(team_id) for team_id in sorted(self._teams)]
            return {
                "team_count": len(teams),
                "agent_count": len({agent for team in self._teams.values() for agent in team.agent_ids}),
                "teams": teams,
            }

    def list_teams(self) -> list[EngineeringTeam]:
        with self._lock:
            return [copy.deepcopy(self._teams[team_id]) for team_id in sorted(self._teams)]

    def _require_team(self, team_id: str) -> EngineeringTeam:
        try:
            return self._teams[team_id]
        except KeyError as exc:
            raise KeyError(f"Team {team_id!r} does not exist.") from exc
