"""
core/hypothesis_engine.py - Autonomous Scientific Hypothesis Generation & Tracking Engine (AutoDev Version 3.6)
Strictly 100% Python Standard Library. Zero external dependencies.
"""

import enum
import hashlib
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.reasoning_cache import ReasoningCache


class HypothesisStatus(str, enum.Enum):
    """Lifecycle state of a scientific research hypothesis."""
    PROPOSED = "PROPOSED"
    UNDER_TEST = "UNDER_TEST"
    IN_EXPERIMENTATION = "IN_EXPERIMENTATION"
    CONFIRMED = "CONFIRMED"
    VALIDATED = "VALIDATED"
    FALSIFIED = "FALSIFIED"
    REFUTED = "REFUTED"
    RETIRED = "RETIRED"
    ABANDONED = "ABANDONED"
    ACCEPTED = "ACCEPTED"


class HypothesisPriority(str, enum.Enum):
    """Urgency and expected strategic impact of the hypothesis."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ResearchHypothesis:
    """Scientific research hypothesis formulation with evaluation criteria and lifecycle state."""
    hypothesis_id: str
    statement: str = ""
    rationale: str = ""
    metric_target: str = ""
    expected_effect_direction: str = ""
    target_effect_size: float = 0.0
    priority: HypothesisPriority = HypothesisPriority.MEDIUM
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    p_value: Optional[float] = None
    effect_size: Optional[float] = None
    evidence: str = ""
    rejection_reason: str = ""

    # Extended / backwards-compatible attributes
    title: str = ""
    description: str = ""
    expected_outcome: str = ""
    affected_modules: List[str] = field(default_factory=list)
    evaluation_metric: str = ""
    target_improvement_pct: float = 0.0
    confidence: float = 0.70
    dependencies: List[str] = field(default_factory=list)
    author: str = "ChiefScientist"
    created_at: float = field(default_factory=time.time)
    validated_at: Optional[float] = None
    experiment_ids: List[str] = field(default_factory=list)
    evidence_summary: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.statement and self.title:
            self.statement = self.title
        if not self.title and self.statement:
            self.title = self.statement
        if not self.description and self.rationale:
            self.description = self.rationale
        if not self.rationale and self.description:
            self.rationale = self.description
        if not self.evaluation_metric and self.metric_target:
            self.evaluation_metric = self.metric_target
        if not self.metric_target and self.evaluation_metric:
            self.metric_target = self.evaluation_metric

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "rationale": self.rationale,
            "metric_target": self.metric_target,
            "expected_effect_direction": self.expected_effect_direction,
            "target_effect_size": self.target_effect_size,
            "priority": self.priority.value,
            "status": self.status.value,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "evidence": self.evidence,
            "rejection_reason": self.rejection_reason,
            "title": self.title,
            "description": self.description,
            "expected_outcome": self.expected_outcome,
            "affected_modules": self.affected_modules,
            "evaluation_metric": self.evaluation_metric,
            "target_improvement_pct": self.target_improvement_pct,
            "confidence": round(self.confidence, 4),
            "dependencies": self.dependencies,
            "author": self.author,
            "created_at": self.created_at,
            "validated_at": self.validated_at,
            "experiment_ids": self.experiment_ids,
            "evidence_summary": self.evidence_summary,
            "tags": self.tags,
        }


class HypothesisEngine:
    """
    Autonomous engine that generates, links, ranks, and tracks scientific hypotheses
    driving the research and experimentation lifecycle.
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        cache_manager: Optional[Any] = None,
        cache_root: Optional[str | Path] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._hypotheses: Dict[str, ResearchHypothesis] = {}
        self._tag_index: Dict[str, Set[str]] = {}
        self._module_index: Dict[str, Set[str]] = {}
        self._issue_cache = ReasoningCache(
            "hypotheses",
            project_root=project_root,
            cache_manager=cache_manager,
            cache_root=cache_root,
        )

    def formulate(
        self,
        statement: str,
        rationale: str = "",
        metric_target: str = "",
        expected_effect_direction: str = "decrease",
        target_effect_size: float = 0.0,
        priority: HypothesisPriority = HypothesisPriority.MEDIUM,
        **kwargs: Any,
    ) -> ResearchHypothesis:
        """Formulates and registers a hypothesis with scientific parameters."""
        with self._lock:
            hid = f"HYP-{uuid.uuid4().hex[:8].upper()}"
            hyp = ResearchHypothesis(
                hypothesis_id=hid,
                statement=statement,
                rationale=rationale,
                metric_target=metric_target,
                expected_effect_direction=expected_effect_direction,
                target_effect_size=target_effect_size,
                priority=priority,
                status=HypothesisStatus.PROPOSED,
                title=statement,
                description=rationale,
                **kwargs,
            )
            self._hypotheses[hid] = hyp
            return hyp

    def propose_hypothesis(
        self,
        title: str,
        description: str,
        expected_outcome: str,
        affected_modules: List[str],
        evaluation_metric: str,
        target_improvement_pct: float = 15.0,
        confidence: float = 0.70,
        priority: HypothesisPriority = HypothesisPriority.MEDIUM,
        dependencies: Optional[List[str]] = None,
        author: str = "PrincipalResearcher",
        tags: Optional[List[str]] = None,
    ) -> ResearchHypothesis:
        """Formulates and registers a new research hypothesis (v3.6 standard API)."""
        with self._lock:
            hid = f"HYP-{uuid.uuid4().hex[:8].upper()}"
            hyp = ResearchHypothesis(
                hypothesis_id=hid,
                statement=title,
                rationale=description,
                title=title,
                description=description,
                expected_outcome=expected_outcome,
                affected_modules=affected_modules,
                evaluation_metric=evaluation_metric,
                metric_target=evaluation_metric,
                target_improvement_pct=target_improvement_pct,
                confidence=confidence,
                priority=priority,
                dependencies=dependencies or [],
                status=HypothesisStatus.PROPOSED,
                author=author,
                tags=tags or [],
            )
            self._hypotheses[hid] = hyp

            for tag in hyp.tags:
                self._tag_index.setdefault(tag.lower(), set()).add(hid)
            for mod in hyp.affected_modules:
                self._module_index.setdefault(mod.lower(), set()).add(hid)

            return hyp

    def get(self, hypothesis_id: str) -> Optional[ResearchHypothesis]:
        """Gets hypothesis by ID."""
        with self._lock:
            return self._hypotheses.get(hypothesis_id)

    def get_hypothesis(self, hypothesis_id: str) -> Optional[ResearchHypothesis]:
        return self.get(hypothesis_id)

    def transition_status(self, hypothesis_id: str, status: HypothesisStatus) -> Optional[ResearchHypothesis]:
        """Transitions hypothesis status."""
        with self._lock:
            hyp = self._hypotheses.get(hypothesis_id)
            if not hyp:
                return None
            hyp.status = status
            return hyp

    def confirm(
        self,
        hypothesis_id: str,
        evidence: str = "",
        p_value: Optional[float] = None,
        effect_size: Optional[float] = None,
    ) -> ResearchHypothesis:
        """Confirms hypothesis empirically."""
        with self._lock:
            hyp = self._hypotheses.get(hypothesis_id)
            if not hyp:
                raise ValueError(f"Hypothesis {hypothesis_id} not found")
            hyp.status = HypothesisStatus.CONFIRMED
            hyp.evidence = evidence
            hyp.evidence_summary = evidence
            hyp.p_value = p_value
            hyp.effect_size = effect_size
            hyp.validated_at = time.time()
            hyp.confidence = min(0.99, hyp.confidence + 0.20)
            return hyp

    def falsify(
        self,
        hypothesis_id: str,
        reason: str = "",
        p_value: Optional[float] = None,
    ) -> ResearchHypothesis:
        """Falsifies hypothesis empirically."""
        with self._lock:
            hyp = self._hypotheses.get(hypothesis_id)
            if not hyp:
                raise ValueError(f"Hypothesis {hypothesis_id} not found")
            hyp.status = HypothesisStatus.FALSIFIED
            hyp.rejection_reason = reason
            hyp.p_value = p_value
            hyp.validated_at = time.time()
            hyp.confidence = max(0.01, hyp.confidence - 0.40)
            return hyp

    def retire(self, hypothesis_id: str, reason: str = "") -> ResearchHypothesis:
        """Retires hypothesis."""
        with self._lock:
            hyp = self._hypotheses.get(hypothesis_id)
            if not hyp:
                raise ValueError(f"Hypothesis {hypothesis_id} not found")
            hyp.status = HypothesisStatus.RETIRED
            hyp.rejection_reason = reason
            return hyp

    def get_by_status(self, status: HypothesisStatus) -> List[ResearchHypothesis]:
        """Filters hypotheses by status."""
        with self._lock:
            return [h for h in self._hypotheses.values() if h.status == status]

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self._hypotheses)

    @property
    def confirmed_count(self) -> int:
        with self._lock:
            return sum(1 for h in self._hypotheses.values() if h.status in (HypothesisStatus.CONFIRMED, HypothesisStatus.VALIDATED))

    @property
    def falsified_count(self) -> int:
        with self._lock:
            return sum(1 for h in self._hypotheses.values() if h.status in (HypothesisStatus.FALSIFIED, HypothesisStatus.REFUTED))

    def update_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        evidence: str = "",
        experiment_id: Optional[str] = None,
    ) -> bool:
        with self._lock:
            hyp = self._hypotheses.get(hypothesis_id)
            if not hyp:
                return False
            hyp.status = status
            if evidence:
                hyp.evidence_summary = evidence
                hyp.evidence = evidence
            if experiment_id and experiment_id not in hyp.experiment_ids:
                hyp.experiment_ids.append(experiment_id)
            return True

    def generate_algorithmic_speedup_hypothesis(
        self,
        module_name: str,
        current_algorithm: str,
        proposed_algorithm: str,
        expected_latency_reduction_pct: float = 25.0,
    ) -> ResearchHypothesis:
        title = f"Algorithmic Speedup in {module_name} via {proposed_algorithm}"
        desc = (
            f"Replacing baseline '{current_algorithm}' with proposed '{proposed_algorithm}' "
            f"in {module_name} will reduce execution latency by {expected_latency_reduction_pct:.1f}%."
        )
        outcome = f"Observed execution latency drops by at least {expected_latency_reduction_pct:.1f}% under standard load."
        return self.propose_hypothesis(
            title=title,
            description=desc,
            expected_outcome=outcome,
            affected_modules=[module_name],
            evaluation_metric="LATENCY",
            target_improvement_pct=expected_latency_reduction_pct,
            confidence=0.75,
            priority=HypothesisPriority.HIGH,
            tags=["optimization", "algorithm", module_name.lower()],
        )

    def generate_prompt_compression_hypothesis(
        self,
        module_name: str,
        compression_technique: str,
        target_token_reduction_pct: float = 30.0,
    ) -> ResearchHypothesis:
        title = f"Prompt Compression via {compression_technique} in {module_name}"
        desc = (
            f"Applying {compression_technique} to reasoning prompts in {module_name} "
            f"will reduce token consumption by {target_token_reduction_pct:.1f}% without degrading generation quality."
        )
        outcome = f"Token count reduced by {target_token_reduction_pct:.1f}% while Quality score remains >= 95%."
        return self.propose_hypothesis(
            title=title,
            description=desc,
            expected_outcome=outcome,
            affected_modules=[module_name],
            evaluation_metric="QUALITY",
            target_improvement_pct=target_token_reduction_pct,
            confidence=0.68,
            priority=HypothesisPriority.MEDIUM,
            tags=["prompt-compression", "efficiency", module_name.lower()],
        )

    def generate_resilience_hypothesis(
        self,
        module_name: str,
        retry_strategy: str,
        target_failure_reduction_pct: float = 40.0,
    ) -> ResearchHypothesis:
        title = f"Fault Resilience via {retry_strategy} in {module_name}"
        desc = (
            f"Introducing {retry_strategy} for transient fault handling in {module_name} "
            f"will reduce task failure and regeneration rates by {target_failure_reduction_pct:.1f}%."
        )
        outcome = f"Success rate increases to >= 99% under simulated network partitioning."
        return self.propose_hypothesis(
            title=title,
            description=desc,
            expected_outcome=outcome,
            affected_modules=[module_name],
            evaluation_metric="SUCCESS_RATE",
            target_improvement_pct=target_failure_reduction_pct,
            confidence=0.82,
            priority=HypothesisPriority.HIGH,
            tags=["resilience", "retry", "reliability", module_name.lower()],
        )

    def generate(
        self,
        issue: str,
        context: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[ResearchHypothesis]:
        """Generates stable issue hypotheses without changing legacy random-ID APIs."""
        normalized_issue = str(issue or "").strip()
        cache_key = {"issue": normalized_issue, "context": context or {}, "limit": limit}
        cached = self._issue_cache.get(cache_key)
        if isinstance(cached, list):
            hypotheses = [self._issue_hypothesis_from_dict(item) for item in cached]
        else:
            causes = [
                ("input_validation", "unvalidated or incomplete inputs"),
                ("dependency_state", "an inconsistent dependency state"),
                ("cache_invalidation", "stale cached state"),
                ("ordering", "an execution-order dependency"),
                ("error_handling", "an unhandled failure path"),
            ]
            issue_terms = set(re.findall(r"[a-z0-9_]+", normalized_issue.lower()))
            relevant = [
                item for item in causes
                if set(item[1].split("_")) & issue_terms
                or any(token in normalized_issue.lower() for token in item[0].split("_"))
            ]
            if not relevant:
                relevant = causes[:3]
            module_values = (context or {}).get("affected_modules", [])
            if isinstance(module_values, str):
                module_values = [module_values]
            modules = sorted({str(module) for module in module_values if module})
            hypotheses = []
            for category, cause in relevant[:max(0, limit)]:
                statement = f"If {cause} causes {normalized_issue}, addressing it will reduce recurrence."
                digest = hashlib.sha256(
                    f"{normalized_issue}\0{category}".encode("utf-8")
                ).hexdigest()[:12].upper()
                hypotheses.append(ResearchHypothesis(
                    hypothesis_id=f"HYP-ISSUE-{digest}",
                    statement=statement,
                    rationale=f"Test the proposed {category.replace('_', ' ')} cause against the reported issue.",
                    metric_target="issue_recurrence_rate",
                    expected_effect_direction="decrease",
                    priority=HypothesisPriority.MEDIUM,
                    affected_modules=modules,
                    evaluation_metric="issue_recurrence_rate",
                    confidence=0.55 if relevant == causes[:3] else 0.65,
                    tags=["issue", category],
                    created_at=0.0,
                ))
            self._issue_cache.set(cache_key, [item.to_dict() for item in hypotheses])
        with self._lock:
            for hypothesis in hypotheses:
                self._hypotheses[hypothesis.hypothesis_id] = hypothesis
                for tag in hypothesis.tags:
                    self._tag_index.setdefault(tag, set()).add(hypothesis.hypothesis_id)
                for module in hypothesis.affected_modules:
                    self._module_index.setdefault(module.lower(), set()).add(hypothesis.hypothesis_id)
        return hypotheses

    def rank(self, hypotheses: Optional[List[ResearchHypothesis]] = None) -> List[ResearchHypothesis]:
        """Ranks hypotheses by confidence, priority, and stable identifier."""
        values = list(hypotheses) if hypotheses is not None else list(self._hypotheses.values())
        priority_order = {
            HypothesisPriority.CRITICAL: 4,
            HypothesisPriority.HIGH: 3,
            HypothesisPriority.MEDIUM: 2,
            HypothesisPriority.LOW: 1,
        }
        return sorted(
            values,
            key=lambda item: (
                -item.confidence,
                -priority_order.get(item.priority, 0),
                item.hypothesis_id,
            ),
        )

    def validate(
        self,
        hypothesis: ResearchHypothesis | str,
        evidence: Any,
        supported: bool = True,
    ) -> Optional[ResearchHypothesis]:
        """Records explicit evidence and updates the hypothesis lifecycle."""
        with self._lock:
            target = (
                self._hypotheses.get(hypothesis)
                if isinstance(hypothesis, str)
                else self._hypotheses.get(hypothesis.hypothesis_id, hypothesis)
            )
            if target is None:
                return None
            evidence_text = (
                "; ".join(sorted(str(item) for item in evidence))
                if isinstance(evidence, (list, tuple, set))
                else str(evidence or "")
            )
            target.evidence = evidence_text
            target.evidence_summary = evidence_text
            target.status = HypothesisStatus.VALIDATED if supported else HypothesisStatus.FALSIFIED
            target.confidence = min(0.99, target.confidence + 0.1) if supported else max(0.01, target.confidence - 0.1)
            return target

    def learn(
        self,
        hypothesis: ResearchHypothesis | str,
        outcome: Any,
        supported: bool = True,
    ) -> Optional[ResearchHypothesis]:
        """Records a result as evidence through the same deterministic validation path."""
        return self.validate(hypothesis, outcome, supported=supported)

    def statistics(self) -> Dict[str, Any]:
        return {
            "hypotheses": self.get_summary_statistics(),
            "cache": self._issue_cache.statistics(),
        }

    @staticmethod
    def _issue_hypothesis_from_dict(value: Dict[str, Any]) -> ResearchHypothesis:
        priority = value.get("priority", HypothesisPriority.MEDIUM.value)
        status = value.get("status", HypothesisStatus.PROPOSED.value)
        return ResearchHypothesis(
            hypothesis_id=str(value["hypothesis_id"]),
            statement=str(value.get("statement", "")),
            rationale=str(value.get("rationale", "")),
            metric_target=str(value.get("metric_target", "")),
            expected_effect_direction=str(value.get("expected_effect_direction", "decrease")),
            target_effect_size=float(value.get("target_effect_size", 0.0)),
            priority=HypothesisPriority(priority),
            status=HypothesisStatus(status),
            p_value=value.get("p_value"),
            effect_size=value.get("effect_size"),
            evidence=str(value.get("evidence", "")),
            rejection_reason=str(value.get("rejection_reason", "")),
            title=str(value.get("title", "")),
            description=str(value.get("description", "")),
            expected_outcome=str(value.get("expected_outcome", "")),
            affected_modules=list(value.get("affected_modules", [])),
            evaluation_metric=str(value.get("evaluation_metric", "")),
            target_improvement_pct=float(value.get("target_improvement_pct", 0.0)),
            confidence=float(value.get("confidence", 0.0)),
            dependencies=list(value.get("dependencies", [])),
            author=str(value.get("author", "ChiefScientist")),
            created_at=float(value.get("created_at", 0.0)),
            validated_at=value.get("validated_at"),
            experiment_ids=list(value.get("experiment_ids", [])),
            evidence_summary=str(value.get("evidence_summary", "")),
            tags=list(value.get("tags", [])),
        )

    def list_hypotheses(
        self,
        status: Optional[HypothesisStatus] = None,
        priority: Optional[HypothesisPriority] = None,
        module: Optional[str] = None,
    ) -> List[ResearchHypothesis]:
        with self._lock:
            results = list(self._hypotheses.values())
            if status:
                results = [h for h in results if h.status == status]
            if priority:
                results = [h for h in results if h.priority == priority]
            if module:
                m_lower = module.lower()
                results = [h for h in results if any(m_lower in m.lower() for m in h.affected_modules)]
            return results

    def get_summary_statistics(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._hypotheses)
            by_status = {s.value: 0 for s in HypothesisStatus}
            for h in self._hypotheses.values():
                by_status[h.status.value] += 1

            validated = by_status[HypothesisStatus.VALIDATED.value] + by_status[HypothesisStatus.CONFIRMED.value]
            refuted = by_status[HypothesisStatus.REFUTED.value] + by_status[HypothesisStatus.FALSIFIED.value]
            completed = validated + refuted
            success_rate = (validated / completed * 100.0) if completed > 0 else 0.0

            return {
                "total_hypotheses": total,
                "status_breakdown": by_status,
                "validation_success_rate_pct": round(success_rate, 2),
                "in_flight_count": by_status[HypothesisStatus.IN_EXPERIMENTATION.value] + by_status[HypothesisStatus.UNDER_TEST.value],
            }
