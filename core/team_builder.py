"""Capability-based engineering team formation using the v3.8 agent runtime."""

from __future__ import annotations

from typing import Any, Optional

from core.organization_manager import OrganizationManager


class TeamBuilder:
    """Forms stable teams from registered agent skills, reliability, and workload."""

    ROLE_SKILLS = {
        "Architect": {"architecture", "design"},
        "Planner": {"planning", "implementation"},
        "Backend": {"backend", "implementation", "python"},
        "Frontend": {"frontend", "ui", "javascript", "typescript"},
        "AI Engineer": {"ai", "machine-learning", "llm"},
        "QA": {"testing", "pytest", "qa"},
        "DevOps": {"devops", "infrastructure", "deployment"},
        "Security": {"security"},
        "Documentation": {"documentation", "docs"},
        "Reviewer": {"review", "code-review"},
    }

    def __init__(
        self,
        organization_manager: OrganizationManager,
        runtime: Optional[Any] = None,
        metrics_tracker: Optional[Any] = None,
    ) -> None:
        self.organization_manager = organization_manager
        self.runtime = runtime or organization_manager.runtime
        self.metrics_tracker = metrics_tracker

    def build_team(
        self,
        project_name: str,
        technology_stack: Optional[list[str]] = None,
        project_size: str = "medium",
        required_roles: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        stack = sorted({value.lower() for value in technology_stack or []})
        roles = list(required_roles or self._roles_for(stack, project_size))
        team = self.organization_manager.create_team(
            name=f"{project_name} Engineering",
            capabilities=roles + stack,
        )
        agents = self.runtime.discover(available_only=False) if self.runtime is not None else []
        assigned: set[str] = set()
        assignments: dict[str, str] = {}
        for role in roles:
            candidates = [
                agent for agent in agents
                if agent.agent_id not in assigned and self._matches(agent, role)
            ]
            candidates.sort(key=lambda agent: self._score(agent))
            if candidates:
                agent = candidates[0]
                self.organization_manager.assign_agent(team.team_id, agent.agent_id, role)
                assigned.add(agent.agent_id)
                assignments[role] = agent.agent_id
        result = self.organization_manager.team_status(team.team_id) or team.to_dict()
        result["role_assignments"] = assignments
        result["technology_stack"] = stack
        return result

    def recommend_agents(self, role: str, limit: int = 5) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit must not be negative.")
        agents = self.runtime.discover(available_only=False) if self.runtime is not None else []
        matches = [agent for agent in agents if self._matches(agent, role)]
        return [
            {
                "agent_id": agent.agent_id,
                "role": agent.role.value,
                "score": self._reliability(agent),
                "workload": agent.workload,
            }
            for agent in sorted(matches, key=self._score)[:limit]
        ]

    def _matches(self, agent: Any, role: str) -> bool:
        required = self.ROLE_SKILLS.get(role, {role.lower()})
        capabilities = {value.lower() for value in getattr(agent, "capabilities", [])}
        agent_role = str(getattr(agent, "role", "")).lower()
        return bool(required & capabilities) or role.lower() in agent_role

    def _score(self, agent: Any) -> tuple[int, float, int, int, str]:
        status = getattr(getattr(agent, "status", None), "value", getattr(agent, "status", ""))
        unavailable = status in {"OFFLINE", "FAILED"} or agent.workload >= agent.max_workload
        return (
            int(unavailable),
            -self._reliability(agent),
            int(agent.workload),
            -int(agent.priority),
            str(agent.agent_id),
        )

    def _reliability(self, agent: Any) -> float:
        if self.metrics_tracker is not None:
            metrics = self.metrics_tracker.get_metrics(agent.agent_id)
            if metrics.get("task_count", 0):
                return float(metrics.get("success_rate", 0.0))
        return float(agent.historical_success_rate)

    @classmethod
    def _roles_for(cls, stack: list[str], project_size: str) -> list[str]:
        roles = ["Architect", "Backend", "QA", "Reviewer"]
        if any(item in stack for item in ("javascript", "typescript", "react", "frontend")):
            roles.append("Frontend")
        if any(item in stack for item in ("ai", "ml", "machine-learning", "llm")):
            roles.append("AI Engineer")
        if project_size.lower() in {"large", "enterprise"}:
            roles.extend(["Security", "DevOps", "Documentation"])
        return roles
