"""
core/ab_testing_engine.py - Autonomous A/B/n Statistical Experimentation & Winner Determination Engine (AutoDev Version 3.6)
Strictly 100% Python Standard Library. Zero external dependencies.
"""

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.statistical_analyzer import HypothesisTestResult, StatisticalAnalyzer


@dataclass
class ExperimentArm:
    """An individual treatment arm (Control or Variant candidate) within an A/B/n test."""
    arm_id: str                          # e.g., "CONTROL", "VARIANT_A", "VARIANT_B"
    name: str
    description: str = ""
    traffic_weight: float = 1.0          # Relative traffic split ratio
    measurements: List[float] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        return len(self.measurements)

    def to_dict(self) -> Dict[str, Any]:
        stats = StatisticalAnalyzer.summarize(self.measurements)
        return {
            "arm_id": self.arm_id,
            "name": self.name,
            "description": self.description,
            "traffic_weight": self.traffic_weight,
            "sample_count": self.sample_count,
            "mean": stats.mean,
            "median": stats.median,
            "std_dev": stats.std_dev,
            "p95": StatisticalAnalyzer.percentile(self.measurements, 95.0),
        }


@dataclass
class ABExperiment:
    """Full specification and state of an active or concluded A/B/n test."""
    experiment_id: str
    name: str
    metric_name: str
    higher_is_better: bool = False       # False for latency/memory, True for throughput/quality
    alpha: float = 0.05                  # Desired significance level (default 95% confidence)
    min_sample_size: int = 30            # Minimum observations per arm before concluding
    control_arm_id: str = "CONTROL"
    arms: Dict[str, ExperimentArm] = field(default_factory=dict)
    is_concluded: bool = False
    winner_arm_id: Optional[str] = None
    winner_rationale: str = ""
    statistical_results: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    concluded_at: Optional[float] = None
    description: str = ""

    @property
    def status(self) -> str:
        return "completed" if self.is_concluded else "active"

    @property
    def winner(self) -> Optional[str]:
        return self.winner_arm_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "metric_name": self.metric_name,
            "higher_is_better": self.higher_is_better,
            "alpha": self.alpha,
            "min_sample_size": self.min_sample_size,
            "control_arm_id": self.control_arm_id,
            "arms": {aid: arm.to_dict() for aid, arm in self.arms.items()},
            "is_concluded": self.is_concluded,
            "winner_arm_id": self.winner_arm_id,
            "winner_rationale": self.winner_rationale,
            "statistical_results": self.statistical_results,
            "created_at": self.created_at,
            "concluded_at": self.concluded_at,
        }


class ABTestingEngine:
    """
    Coordinates multi-arm scientific experimentation (Control vs Variants A, B, C...).
    Provides deterministic traffic allocation, observation capture, and automated
    statistical winner determination with Bonferroni correction for multiple hypothesis testing.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._experiments: Dict[str, ABExperiment] = {}

    def create_experiment(
        self,
        name: str,
        metric_name: Optional[str] = None,
        variants: Optional[List[Tuple[str, str]]] = None,  # [(variant_id, variant_name), ...]
        control_name: str = "Current Production Baseline",
        higher_is_better: bool = False,
        alpha: float = 0.05,
        min_sample_size: Optional[int] = None,
        traffic_weights: Optional[Dict[str, float]] = None,
        *,
        description: str = "",
        traffic_split: Optional[Dict[str, float]] = None,
        metric_of_interest: Optional[str] = None,
    ) -> ABExperiment:
        """Initializes a new multi-arm experiment with Control and specified variants."""
        with self._lock:
            exp_id = f"EXP-{uuid.uuid4().hex[:8].upper()}"
            metric_name = metric_name or metric_of_interest or "metric"
            legacy_split = traffic_split is not None
            if legacy_split:
                split = traffic_split or {}
                if not split:
                    raise ValueError("traffic_split must contain at least one arm")
                arms = {
                    arm_id: ExperimentArm(
                        arm_id=arm_id,
                        name=arm_id,
                        traffic_weight=float(weight),
                    )
                    for arm_id, weight in split.items()
                }
                control_id = next(
                    (arm_id for arm_id in arms if arm_id.casefold() == "control"),
                    next(iter(arms)),
                )
                if min_sample_size is None:
                    min_sample_size = 1
            else:
                arms = {
                    "CONTROL": ExperimentArm(
                        arm_id="CONTROL",
                        name=control_name,
                        traffic_weight=(traffic_weights or {}).get("CONTROL", 1.0),
                    )
                }
                for vid, vname in variants or []:
                    arms[vid] = ExperimentArm(
                        arm_id=vid,
                        name=vname,
                        traffic_weight=(traffic_weights or {}).get(vid, 1.0),
                    )
                control_id = "CONTROL"
            weights = traffic_weights or {}

            exp = ABExperiment(
                experiment_id=exp_id,
                name=name,
                metric_name=metric_name,
                higher_is_better=higher_is_better,
                alpha=alpha,
                min_sample_size=min_sample_size if min_sample_size is not None else 30,
                control_arm_id=control_id,
                arms=arms,
                description=description,
            )

            self._experiments[exp_id] = exp
            return exp

    def assign_arm(self, experiment_id: str, entity_id: str) -> str:
        return self.route_traffic(experiment_id, entity_id)

    def evaluate(self, experiment_id: str) -> Dict[str, Any]:
        result = self.evaluate_and_determine_winner(experiment_id)
        experiment = self.get_experiment(experiment_id)
        if experiment is None:
            return result
        evaluations = result.get("evaluations", {})
        p_values = [
            item.get("t_test", {}).get("p_value", 1.0)
            for item in evaluations.values()
            if isinstance(item, dict) and item.get("t_test")
        ]
        return {
            **result,
            "is_conclusive": experiment.is_concluded,
            "winner": experiment.winner_arm_id,
            "p_value": min(p_values, default=1.0),
        }

    def conclude(self, experiment_id: str) -> Optional[ABExperiment]:
        self.evaluate_and_determine_winner(experiment_id)
        experiment = self.get_experiment(experiment_id)
        if experiment is not None and not experiment.is_concluded:
            sampled_arms = [arm for arm in experiment.arms.values() if arm.sample_count]
            if sampled_arms and all(arm.sample_count >= experiment.min_sample_size for arm in sampled_arms):
                experiment.is_concluded = True
                experiment.winner_arm_id = experiment.control_arm_id
                experiment.concluded_at = time.time()
        return experiment

    def get_experiment(self, experiment_id: str) -> Optional[ABExperiment]:
        with self._lock:
            return self._experiments.get(experiment_id)

    def route_traffic(self, experiment_id: str, routing_key: str) -> str:
        """
        Deterministically maps a routing key (e.g. task ID or user key) to an experiment arm
        proportional to traffic weights using SHA-256 hashing.
        """
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if not exp:
                raise ValueError(f"Experiment '{experiment_id}' not found")

            # Compute SHA-256 integer hash
            h_int = int(hashlib.sha256(f"{experiment_id}:{routing_key}".encode('utf-8')).hexdigest()[:8], 16)
            total_weight = sum(arm.traffic_weight for arm in exp.arms.values())
            if total_weight <= 0:
                return exp.control_arm_id

            target_val = (h_int % 10000) / 10000.0 * total_weight
            accum = 0.0
            for aid, arm in exp.arms.items():
                accum += arm.traffic_weight
                if accum >= target_val:
                    return aid

            return exp.control_arm_id

    def record_observation(self, experiment_id: str, arm_id: str, value: float) -> bool:
        """Appends an empirical observation to the specified treatment arm."""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if not exp or exp.is_concluded:
                return False

            arm = exp.arms.get(arm_id)
            if not arm:
                return False

            arm.measurements.append(float(value))
            return True

    def evaluate_and_determine_winner(self, experiment_id: str) -> Dict[str, Any]:
        """
        Performs hypothesis testing comparing Control against each Variant arm.
        Applies Bonferroni multiple-comparison correction (alpha / k).
        Automatically declares a statistically significant winner if verified.
        """
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if not exp:
                return {"error": "Experiment not found"}

            control_arm = exp.arms.get(exp.control_arm_id)
            if not control_arm or control_arm.sample_count < exp.min_sample_size:
                return {
                    "status": "INSUFFICIENT_DATA",
                    "message": f"Control has {control_arm.sample_count if control_arm else 0} samples (minimum required: {exp.min_sample_size})",
                }

            variant_arms = [arm for aid, arm in exp.arms.items() if aid != exp.control_arm_id]
            k = max(1, len(variant_arms))
            # Bonferroni corrected significance threshold
            corrected_alpha = exp.alpha / k

            control_mean = StatisticalAnalyzer.mean(control_arm.measurements)
            evaluations: Dict[str, Any] = {}
            candidate_winners: List[Tuple[str, float, float, HypothesisTestResult]] = []

            for var in variant_arms:
                if var.sample_count < exp.min_sample_size:
                    evaluations[var.arm_id] = {
                        "status": "INSUFFICIENT_DATA",
                        "sample_count": var.sample_count,
                    }
                    continue

                var_mean = StatisticalAnalyzer.mean(var.measurements)
                # Statistical test (Student's t-test with Welch correction)
                t_res = StatisticalAnalyzer.t_test_two_sample(
                    sample_a=var.measurements,
                    sample_b=control_arm.measurements,
                    alpha=corrected_alpha,
                )
                # Non-parametric validation (Mann-Whitney U)
                u_res = StatisticalAnalyzer.mann_whitney_u(
                    sample_a=var.measurements,
                    sample_b=control_arm.measurements,
                    alpha=corrected_alpha,
                )

                delta = var_mean - control_mean
                delta_pct = (delta / control_mean * 100.0) if abs(control_mean) > 1e-9 else 0.0

                is_improvement = (delta > 0) if exp.higher_is_better else (delta < 0)
                is_statistically_significant = t_res.p_value < corrected_alpha

                evaluations[var.arm_id] = {
                    "variant_name": var.name,
                    "sample_count": var.sample_count,
                    "mean": round(var_mean, 6),
                    "control_mean": round(control_mean, 6),
                    "delta": round(delta, 6),
                    "delta_pct": round(delta_pct, 4),
                    "t_test": t_res.to_dict(),
                    "mann_whitney": u_res.to_dict(),
                    "is_improvement": is_improvement,
                    "is_statistically_significant": is_statistically_significant,
                }

                if is_improvement and is_statistically_significant:
                    candidate_winners.append((var.arm_id, abs(delta_pct), t_res.p_value, t_res))

            # Select the most effective statistically significant winner
            exp.statistical_results = evaluations

            if candidate_winners:
                # Rank by effect size
                candidate_winners.sort(key=lambda t: t[1], reverse=True)
                top_aid, top_delta_pct, p_val, top_test = candidate_winners[0]
                exp.is_concluded = True
                exp.winner_arm_id = top_aid
                exp.concluded_at = time.time()
                exp.winner_rationale = (
                    f"Variant '{top_aid}' declared statistically significant winner with "
                    f"{top_delta_pct:.2f}% improvement over Control (p={p_val:.6f} < {corrected_alpha:.6f}, "
                    f"Cohen's d={top_test.effect_size:.2f})."
                )
            else:
                # Check if all variants are sufficiently sampled
                all_sampled = all(v.sample_count >= exp.min_sample_size for v in variant_arms)
                if all_sampled:
                    exp.is_concluded = True
                    exp.winner_arm_id = exp.control_arm_id
                    exp.concluded_at = time.time()
                    exp.winner_rationale = (
                        "No variant demonstrated a statistically significant improvement over Control. "
                        "Retaining Control baseline."
                    )

            return {
                "experiment_id": exp.experiment_id,
                "is_concluded": exp.is_concluded,
                "winner_arm_id": exp.winner_arm_id,
                "winner_rationale": exp.winner_rationale,
                "evaluations": evaluations,
            }
