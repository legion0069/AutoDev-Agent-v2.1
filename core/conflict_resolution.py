"""Deterministic conflict detection and policy-driven resolution."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class ConflictKind(str, Enum):
    FILE_OWNERSHIP = "file_ownership"
    PARALLEL_EDIT = "parallel_edit"
    RESOURCE_CONTENTION = "resource_contention"
    CONTRADICTING_DECISION = "contradicting_decision"
    ARCHITECTURE_DISAGREEMENT = "architecture_disagreement"


@dataclass
class CollaborationConflict:
    conflict_id: str
    kind: ConflictKind
    resource: str
    participants: list[str]
    details: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    winner: Optional[str] = None
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "kind": self.kind.value,
            "resource": self.resource,
            "participants": list(self.participants),
            "details": dict(self.details),
            "resolved": self.resolved,
            "winner": self.winner,
            "resolution": self.resolution,
        }


class ConflictResolutionEngine:
    """Detects concurrent resource/decision conflicts and resolves them by stable policy."""

    POLICIES = {"first_agent", "highest_priority", "prefer_agent", "consensus", "reject"}

    def __init__(
        self,
        policy: str = "highest_priority",
        preferred_agent: Optional[str] = None,
    ) -> None:
        if policy not in self.POLICIES:
            raise ValueError(f"Unsupported conflict policy: {policy}")
        self.policy = policy
        self.preferred_agent = preferred_agent
        self._lock = threading.RLock()
        self._conflicts: dict[str, CollaborationConflict] = {}

    def detect_conflicts(
        self,
        tasks: Optional[list[Any]] = None,
        decisions: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> list[CollaborationConflict]:
        found: list[CollaborationConflict] = []
        resource_owners: dict[str, list[tuple[str, Any]]] = {}
        for task in tasks or []:
            agent = str(self._get(task, "agent_id", self._get(task, "assigned_agent_id", "")))
            resources = self._get(
                task,
                "files",
                self._get(task, "resources", self._get(task, "estimated_files", [])),
            )
            if isinstance(resources, str):
                resources = [resources]
            for resource in sorted({str(item) for item in resources or []}):
                resource_owners.setdefault(resource, []).append((agent, task))
        for resource, owners in sorted(resource_owners.items()):
            participants = sorted({agent for agent, _ in owners if agent})
            if len(participants) > 1:
                found.append(self._create(
                    ConflictKind.FILE_OWNERSHIP,
                    resource,
                    participants,
                    {"tasks": sorted(str(self._get(task, "id", self._get(task, "task_id", ""))) for _, task in owners)},
                ))
        for resource, owners in sorted(resource_owners.items()):
            participants = sorted({agent for agent, _ in owners if agent})
            if len(owners) > 1 and len(participants) > 1:
                found.append(self._create(
                    ConflictKind.RESOURCE_CONTENTION,
                    resource,
                    participants,
                    {"task_count": len(owners)},
                ))
        if decisions:
            values: dict[str, dict[str, list[str]]] = {}
            for agent, proposal in sorted(decisions.items()):
                for key, value in sorted(proposal.items()):
                    values.setdefault(str(key), {}).setdefault(str(value), []).append(str(agent))
            for key, proposals in sorted(values.items()):
                if len(proposals) > 1:
                    participants = sorted({agent for agents in proposals.values() for agent in agents})
                    found.append(self._create(
                        ConflictKind.ARCHITECTURE_DISAGREEMENT,
                        key,
                        participants,
                        {"proposals": {value: sorted(agents) for value, agents in sorted(proposals.items())}},
                    ))
                    found.append(self._create(
                        ConflictKind.CONTRADICTING_DECISION,
                        key,
                        participants,
                        {"proposals": {value: sorted(agents) for value, agents in sorted(proposals.items())}},
                    ))
        with self._lock:
            for conflict in found:
                self._conflicts[conflict.conflict_id] = conflict
        return sorted(found, key=lambda conflict: (conflict.kind.value, conflict.resource, conflict.conflict_id))

    def resolve(
        self,
        conflict: CollaborationConflict | str,
        policy: Optional[str] = None,
        priorities: Optional[Mapping[str, float]] = None,
    ) -> CollaborationConflict:
        record = self._conflicts.get(conflict) if isinstance(conflict, str) else conflict
        if record is None:
            raise KeyError(f"Unknown conflict: {conflict}")
        selected_policy = policy or self.policy
        if selected_policy not in self.POLICIES:
            raise ValueError(f"Unsupported conflict policy: {selected_policy}")
        if record.resolved:
            return record
        participants = sorted(record.participants)
        winner: Optional[str] = None
        if selected_policy == "first_agent":
            winner = participants[0] if participants else None
        elif selected_policy == "highest_priority":
            scores = priorities or {}
            winner = min(participants, key=lambda item: (-float(scores.get(item, 0.0)), item)) if participants else None
        elif selected_policy == "prefer_agent":
            if self.preferred_agent not in participants:
                raise ValueError("preferred_agent must be one of the conflict participants")
            winner = self.preferred_agent
        elif selected_policy == "consensus":
            record.resolution = "escalated_to_consensus"
            return record
        else:
            record.resolution = "all_proposals_rejected"
        record.winner = winner
        record.resolved = selected_policy != "consensus"
        if selected_policy not in {"consensus", "reject"}:
            record.resolution = f"selected {winner} using {selected_policy}"
        with self._lock:
            self._conflicts[record.conflict_id] = record
        return record

    def conflicts(self) -> list[CollaborationConflict]:
        with self._lock:
            return [self._conflicts[key] for key in sorted(self._conflicts)]

    @staticmethod
    def _get(value: Any, name: str, default: Any = None) -> Any:
        return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)

    @staticmethod
    def _create(
        kind: ConflictKind,
        resource: str,
        participants: list[str],
        details: dict[str, Any],
    ) -> CollaborationConflict:
        material = repr((kind.value, resource, participants, sorted(details.items())))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return CollaborationConflict(
            conflict_id=f"conflict-{digest}",
            kind=kind,
            resource=resource,
            participants=participants,
            details=details,
        )
