"""Explainable consensus interface backed by AutoDev's established voting engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.multi_agent.agent_registry import AgentRole
from core.multi_agent.consensus_engine import (
    ConsensusEngine as LegacyConsensusEngine,
    ConsensusStrategy,
    ReviewVote,
    VoteDecision,
)


@dataclass(frozen=True)
class ConsensusResult:
    approved: bool
    strategy: str
    reason: str
    vote_count: int
    approval_count: int
    rejection_count: int
    confidence: float
    evidence: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "strategy": self.strategy,
            "reason": self.reason,
            "vote_count": self.vote_count,
            "approval_count": self.approval_count,
            "rejection_count": self.rejection_count,
            "confidence": self.confidence,
            "evidence": [dict(vote) for vote in self.evidence],
        }


class ConsensusEngine(LegacyConsensusEngine):
    """Adds a direct explainable vote API while preserving proposal-based methods."""

    def __init__(self) -> None:
        super().__init__()
        self._decision_sequence = 0

    def decide(
        self,
        votes: Iterable[ReviewVote | dict[str, Any]],
        strategy: ConsensusStrategy | str = ConsensusStrategy.MAJORITY,
        proposal_id: str = "decision",
    ) -> ConsensusResult:
        selected_strategy = (
            strategy if isinstance(strategy, ConsensusStrategy) else ConsensusStrategy(strategy)
        )
        with self._lock:
            self._decision_sequence += 1
            decision_id = f"{proposal_id}-{self._decision_sequence:08d}"
        proposal = self.create_proposal(
            proposal_id=decision_id,
            title="Engineering decision",
            description="Deterministic multi-agent vote",
            strategy=selected_strategy,
        )
        normalized = [self._normalize_vote(vote) for vote in votes]
        for vote in normalized:
            self.cast_vote(decision_id, vote)
        approved, reason, metrics = self.evaluate_consensus(decision_id)
        evidence = tuple(
            sorted(
                (vote.to_dict() for vote in normalized),
                key=lambda vote: (vote["reviewer_id"], vote["decision"]),
            )
        )
        return ConsensusResult(
            approved=approved,
            strategy=selected_strategy.value,
            reason=reason,
            vote_count=int(metrics.get("active_votes", metrics.get("total_votes", 0))),
            approval_count=int(metrics.get("approvals_count", 0)),
            rejection_count=int(metrics.get("rejections_count", 0)),
            confidence=round(float(metrics.get("avg_confidence", 0.0)), 4),
            evidence=evidence,
        )

    @staticmethod
    def _normalize_vote(vote: ReviewVote | dict[str, Any]) -> ReviewVote:
        if isinstance(vote, ReviewVote):
            return vote
        role = vote.get("reviewer_role", AgentRole.TASK_SCHEDULER)
        if isinstance(role, str):
            role = AgentRole(role)
        decision = vote.get("decision", VoteDecision.ABSTAIN)
        if isinstance(decision, str):
            decision = VoteDecision(decision.lower())
        return ReviewVote(
            reviewer_id=str(vote["reviewer_id"]),
            reviewer_role=role,
            decision=decision,
            quality_score=float(vote.get("quality_score", 80.0)),
            confidence_score=max(0.0, min(1.0, float(vote.get("confidence_score", 0.85)))),
            rationale=str(vote.get("rationale", "")),
            timestamp=0.0,
        )
