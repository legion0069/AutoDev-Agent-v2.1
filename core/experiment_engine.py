"""
core/experiment_engine.py - Full Lifecycle Scientific Experimentation Engine (AutoDev Version 3.6)
Strictly 100% Python Standard Library. Zero external dependencies.
"""

import enum
import inspect
import math
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from core.ab_testing_engine import ABTestingEngine
from core.hypothesis_engine import HypothesisEngine, HypothesisStatus, ResearchHypothesis
from core.reproducibility_manager import ReproducibilityManager
from core.research_memory import ResearchMemory
from core.scientific_logger import ScientificEventType, ScientificLogger
from core.statistical_analyzer import StatisticalAnalyzer


class ExperimentLifecycleStage(str, enum.Enum):
    """Rigorous sequential stages of the scientific experiment lifecycle."""
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    MEASUREMENT = "MEASUREMENT"
    VALIDATION = "VALIDATION"
    COMPARISON = "COMPARISON"
    STATISTICAL_ANALYSIS = "STATISTICAL_ANALYSIS"
    RESULT_CLASSIFICATION = "RESULT_CLASSIFICATION"
    CONCLUDED = "CONCLUDED"
    FAILED = "FAILED"


class ExperimentOutcome(str, enum.Enum):
    """Empirical determination of the hypothesis test."""
    SUPPORTED = "SUPPORTED"          # Statistically significant improvement confirmed
    REFUTED = "REFUTED"              # Significant degradation or null outcome disproving hypothesis
    INCONCLUSIVE = "INCONCLUSIVE"    # Insufficient effect size or p >= alpha


class ExperimentStage(str, enum.Enum):
    """Legacy lifecycle stages retained for callers of create_experiment()."""

    PROPOSED = "PROPOSED"
    DESIGNED = "DESIGNED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ScientificExperiment:
    """Legacy experiment record used by the staged lifecycle API."""

    experiment_id: str
    name: str
    hypothesis_statement: str
    candidate_code: str
    baseline_code: str
    stage: ExperimentStage = ExperimentStage.PROPOSED


@dataclass
class ExperimentRecord:
    """Comprehensive immutable record of an experimental trial."""
    experiment_id: str
    title: str
    hypothesis_id: Optional[str]
    metric_name: str
    stage: ExperimentLifecycleStage
    outcome: Optional[ExperimentOutcome] = None
    control_stats: Optional[Dict[str, Any]] = None
    variant_stats: Optional[Dict[str, Any]] = None
    statistical_test: Optional[Dict[str, Any]] = None
    manifest_id: Optional[str] = None
    winner_arm: Optional[str] = None
    summary_report: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "title": self.title,
            "hypothesis_id": self.hypothesis_id,
            "metric_name": self.metric_name,
            "stage": self.stage.value,
            "outcome": self.outcome.value if self.outcome else None,
            "control_stats": self.control_stats,
            "variant_stats": self.variant_stats,
            "statistical_test": self.statistical_test,
            "manifest_id": self.manifest_id,
            "winner_arm": self.winner_arm,
            "summary_report": self.summary_report,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class ExperimentEngine:
    """
    Executes the complete 8-stage scientific experiment lifecycle:
    Planning -> Execution -> Measurement -> Validation -> Comparison -> Statistical Analysis -> Classification -> Archival.
    """

    def __init__(
        self,
        hypothesis_engine: Optional[HypothesisEngine] = None,
        ab_testing_engine: Optional[ABTestingEngine] = None,
        reproducibility_manager: Optional[ReproducibilityManager] = None,
        scientific_logger: Optional[ScientificLogger] = None,
        research_memory: Optional[ResearchMemory] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.hypothesis_engine = hypothesis_engine or HypothesisEngine()
        self.ab_testing_engine = ab_testing_engine or ABTestingEngine()
        self.reproducibility_manager = reproducibility_manager or ReproducibilityManager()
        self.scientific_logger = scientific_logger or ScientificLogger()
        self.research_memory = research_memory or ResearchMemory()
        self._experiments: Dict[str, ExperimentRecord] = {}
        self._legacy_experiments: Dict[str, ScientificExperiment] = {}

    def create_experiment(
        self,
        name: str,
        hypothesis_statement: str,
        candidate_code: str,
        baseline_code: str,
    ) -> ScientificExperiment:
        """Creates a proposed experiment using the legacy staged API."""
        experiment = ScientificExperiment(
            experiment_id=f"EXP-{uuid.uuid4().hex[:8].upper()}",
            name=name,
            hypothesis_statement=hypothesis_statement,
            candidate_code=candidate_code,
            baseline_code=baseline_code,
        )
        with self._lock:
            self._legacy_experiments[experiment.experiment_id] = experiment
        return experiment

    def transition_stage(
        self,
        experiment_id: str,
        stage: ExperimentStage,
    ) -> ScientificExperiment:
        """Advances a legacy experiment through its ordered lifecycle."""
        with self._lock:
            experiment = self._legacy_experiments.get(experiment_id)
            if experiment is None:
                raise KeyError(f"Experiment {experiment_id!r} not found")
            allowed = {
                ExperimentStage.PROPOSED: {ExperimentStage.DESIGNED, ExperimentStage.FAILED},
                ExperimentStage.DESIGNED: {ExperimentStage.EXECUTING, ExperimentStage.FAILED},
                ExperimentStage.EXECUTING: {ExperimentStage.COMPLETED, ExperimentStage.FAILED},
                ExperimentStage.COMPLETED: set(),
                ExperimentStage.FAILED: set(),
            }
            if stage not in allowed[experiment.stage]:
                raise ValueError(
                    f"Invalid experiment stage transition: {experiment.stage.value} -> {stage.value}"
                )
            experiment.stage = stage
            return experiment

    def get_experiment(
        self,
        experiment_id: str,
    ) -> Optional[ExperimentRecord | ScientificExperiment]:
        with self._lock:
            return self._legacy_experiments.get(experiment_id) or self._experiments.get(experiment_id)

    def run_experiment(
        self,
        title: str,
        metric_name: str,
        control_evaluator: Callable[[], float],
        variant_evaluator: Callable[[], float],
        hypothesis: Optional[ResearchHypothesis] = None,
        sample_size: int = 35,
        alpha: float = 0.05,
        higher_is_better: bool = False,
        seed: int = 42,
    ) -> ExperimentRecord:
        """
        Executes the full scientific experiment lifecycle synchronously from planning to conclusion.
        """
        with self._lock:
            exp_id = f"EXP-{uuid.uuid4().hex[:8].upper()}"
            hyp_id = hypothesis.hypothesis_id if hypothesis else None

            # --- Stage 1: Planning ---
            record = ExperimentRecord(
                experiment_id=exp_id,
                title=title,
                hypothesis_id=hyp_id,
                metric_name=metric_name,
                stage=ExperimentLifecycleStage.PLANNING,
            )
            self._experiments[exp_id] = record

            if hyp_id:
                self.hypothesis_engine.update_status(hyp_id, HypothesisStatus.IN_EXPERIMENTATION, experiment_id=exp_id)

            self.scientific_logger.log_event(
                event_type=ScientificEventType.EXPERIMENT_START,
                actor="ExperimentEngine",
                entity_id=exp_id,
                payload={"title": title, "metric": metric_name, "sample_size": sample_size},
            )

            # --- Stage 2 & 3: Execution & Measurement ---
            record.stage = ExperimentLifecycleStage.EXECUTION
            control_samples: List[float] = []
            variant_samples: List[float] = []

            for _ in range(sample_size):
                control_samples.append(float(control_evaluator()))
                variant_samples.append(float(variant_evaluator()))

            record.stage = ExperimentLifecycleStage.MEASUREMENT
            c_stats = StatisticalAnalyzer.summarize(control_samples)
            v_stats = StatisticalAnalyzer.summarize(variant_samples)
            record.control_stats = c_stats.to_dict()
            record.variant_stats = v_stats.to_dict()

            # --- Stage 4: Validation (Reproducibility Manifest) ---
            record.stage = ExperimentLifecycleStage.VALIDATION
            manifest = self.reproducibility_manager.record_manifest(
                experiment_id=exp_id,
                seed=seed,
                config={"metric_name": metric_name, "sample_size": sample_size, "alpha": alpha},
                inputs={"sample_size": sample_size},
                outputs={"control_mean": c_stats.mean, "variant_mean": v_stats.mean},
                execution_logs=[f"Collected {sample_size} observations per arm."],
                code_snippet=title,
            )
            record.manifest_id = manifest.manifest_id

            # --- Stage 5: Comparison ---
            record.stage = ExperimentLifecycleStage.COMPARISON
            delta = v_stats.mean - c_stats.mean
            delta_pct = (delta / c_stats.mean * 100.0) if abs(c_stats.mean) > 1e-9 else 0.0

            # --- Stage 6: Statistical Analysis ---
            record.stage = ExperimentLifecycleStage.STATISTICAL_ANALYSIS
            t_res = StatisticalAnalyzer.t_test_two_sample(
                sample_a=variant_samples,
                sample_b=control_samples,
                alpha=alpha,
            )
            record.statistical_test = t_res.to_dict()

            # --- Stage 7: Result Classification ---
            record.stage = ExperimentLifecycleStage.RESULT_CLASSIFICATION
            is_improvement = (delta > 0) if higher_is_better else (delta < 0)

            if t_res.is_significant and is_improvement:
                outcome = ExperimentOutcome.SUPPORTED
                winner = "VARIANT"
                summary = (
                    f"Hypothesis SUPPORTED: Variant achieved {abs(delta_pct):.2f}% improvement "
                    f"in {metric_name} with statistical significance (p={t_res.p_value:.6f} < {alpha}, "
                    f"Cohen's d={t_res.effect_size or 0.0:.2f})."
                )
                if hyp_id:
                    self.hypothesis_engine.update_status(hyp_id, HypothesisStatus.VALIDATED, evidence=summary)
                self.research_memory.record_success(
                    experiment_id=exp_id,
                    breakthrough_summary=summary,
                    performance_gain_pct=abs(delta_pct),
                )
            elif t_res.is_significant and not is_improvement:
                outcome = ExperimentOutcome.REFUTED
                winner = "CONTROL"
                summary = (
                    f"Hypothesis REFUTED: Variant caused a statistically significant {abs(delta_pct):.2f}% degradation "
                    f"in {metric_name} (p={t_res.p_value:.6f} < {alpha})."
                )
                if hyp_id:
                    self.hypothesis_engine.update_status(hyp_id, HypothesisStatus.REFUTED, evidence=summary)
                self.research_memory.record_failure(
                    experiment_id=exp_id,
                    description=summary,
                    root_cause=f"Unfavorable trade-off in {metric_name}",
                    lessons_learned="Avoid variant design under current workload conditions.",
                )
            else:
                outcome = ExperimentOutcome.INCONCLUSIVE
                winner = "CONTROL"
                summary = (
                    f"Experiment INCONCLUSIVE: Observed delta of {delta_pct:.2f}% is not statistically significant "
                    f"(p={t_res.p_value:.4f} >= {alpha}). Null hypothesis cannot be rejected."
                )

            record.outcome = outcome
            record.winner_arm = winner
            record.summary_report = summary
            record.stage = ExperimentLifecycleStage.CONCLUDED
            record.completed_at = time.time()

            # Store in research memory & scientific logger
            self.research_memory.store_experiment(exp_id, record.to_dict())
            self.scientific_logger.log_event(
                event_type=ScientificEventType.EXPERIMENT_COMPLETE,
                actor="ExperimentEngine",
                entity_id=exp_id,
                payload={"outcome": outcome.value, "winner": winner, "delta_pct": delta_pct, "p_value": t_res.p_value},
            )

            return record

    def get_experiment(
        self,
        experiment_id: str,
    ) -> Optional[ExperimentRecord | ScientificExperiment]:
        with self._lock:
            return self._legacy_experiments.get(experiment_id) or self._experiments.get(experiment_id)


class EvolutionExperimentEngine:
    """Runs trusted candidate callables in disposable, per-sample workspaces.

    Workspaces isolate candidate-created files but are not an operating-system
    security boundary. Only trusted evaluator callables should be supplied.
    """

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        if self.workspace_root is not None:
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._experiments: dict[str, dict[str, Any]] = {}
        self._sequence = 0

    def create_experiment(
        self,
        name: str,
        baseline_runner: Callable[[Path], float] | None = None,
        candidate_runners: Mapping[str, Callable[[Path], float]] | None = None,
        *,
        higher_is_better: bool = False,
        sample_size: int = 5,
        alpha: float = 0.05,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Experiment name must not be empty.")
        if sample_size < 2:
            raise ValueError("sample_size must be at least 2.")
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be between 0 and 1.")
        runners = dict(candidate_runners or {})
        if any(not key.strip() for key in runners):
            raise ValueError("Candidate names must not be empty.")
        if any(not callable(runner) for runner in runners.values()):
            raise TypeError("Each candidate runner must be callable.")
        if baseline_runner is not None and not callable(baseline_runner):
            raise TypeError("baseline_runner must be callable.")

        self._sequence += 1
        experiment_id = f"V40-EXP-{self._sequence:04d}"
        record = {
            "experiment_id": experiment_id,
            "name": name,
            "status": "planned",
            "higher_is_better": higher_is_better,
            "sample_size": sample_size,
            "alpha": alpha,
            "baseline_samples": [],
            "candidate_samples": {},
            "candidate_results": {},
            "winner": None,
            "rollback_status": "not_required",
        }
        self._experiments[experiment_id] = {
            "record": record,
            "baseline_runner": baseline_runner,
            "candidate_runners": dict(sorted(runners.items())),
        }
        return self._copy_record(record)

    def run(
        self,
        experiment_id: str,
        *,
        sample_size: int | None = None,
    ) -> dict[str, Any]:
        experiment = self._get_experiment(experiment_id)
        record = experiment["record"]
        baseline_runner = experiment["baseline_runner"]
        candidates = experiment["candidate_runners"]
        if baseline_runner is None:
            raise ValueError("A baseline_runner is required to run this experiment.")
        if not candidates:
            raise ValueError("At least one candidate runner is required to run this experiment.")
        count = record["sample_size"] if sample_size is None else sample_size
        if count < 2:
            raise ValueError("sample_size must be at least 2.")
        record["status"] = "running"
        record["sample_size"] = count
        try:
            baseline = self._measure(baseline_runner, experiment_id, "baseline", count)
            candidate_samples = {
                name: self._measure(runner, experiment_id, name, count)
                for name, runner in candidates.items()
            }
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["rollback_status"] = "isolated_workspace_discarded"
            raise
        record["baseline_samples"] = baseline
        record["candidate_samples"] = candidate_samples
        record["status"] = "completed"
        return self.compare(experiment_id)

    def compare(self, experiment_id: str) -> dict[str, Any]:
        record = self._get_experiment(experiment_id)["record"]
        baseline = record["baseline_samples"]
        if not baseline:
            raise ValueError("Experiment has no completed baseline measurements.")
        higher_is_better = record["higher_is_better"]
        comparisons: dict[str, Any] = {}
        winners: list[tuple[float, str]] = []
        for name, samples in sorted(record["candidate_samples"].items()):
            test = StatisticalAnalyzer.t_test_two_sample(
                sample_a=samples,
                sample_b=baseline,
                alpha=record["alpha"],
            )
            candidate_mean = StatisticalAnalyzer.mean(samples)
            baseline_mean = StatisticalAnalyzer.mean(baseline)
            improved = candidate_mean > baseline_mean if higher_is_better else candidate_mean < baseline_mean
            comparisons[name] = {
                "candidate_mean": candidate_mean,
                "baseline_mean": baseline_mean,
                "statistical_test": test.to_dict(),
                "is_improvement": improved,
                "is_significant": test.is_significant,
            }
            if test.is_significant and improved:
                winners.append((-candidate_mean if higher_is_better else candidate_mean, name))
        record["candidate_results"] = comparisons
        record["winner"] = min(winners)[1] if winners else None
        if record["winner"] is None:
            record["rollback_status"] = "isolated_workspace_discarded"
        return self._copy_record(record)

    def rollback(self, experiment_id: str) -> dict[str, Any]:
        """Discards the isolated result and clears any selected candidate."""
        record = self._get_experiment(experiment_id)["record"]
        record["winner"] = None
        record["rollback_status"] = "isolated_workspace_discarded"
        record["status"] = "rolled_back"
        return self._copy_record(record)

    def history(self) -> list[dict[str, Any]]:
        return [self._copy_record(self._experiments[key]["record"]) for key in sorted(self._experiments)]

    def _measure(
        self,
        runner: Callable[[Path], float],
        experiment_id: str,
        label: str,
        count: int,
    ) -> list[float]:
        samples = []
        for sample_index in range(count):
            with tempfile.TemporaryDirectory(
                prefix=f"autodev-{experiment_id}-{label}-{sample_index}-",
                dir=self.workspace_root,
            ) as directory:
                workspace = Path(directory)
                inspect.signature(runner).bind(workspace)
                value = float(runner(workspace))
                if not math.isfinite(value):
                    raise ValueError(f"Runner {label!r} returned a non-finite measurement.")
                samples.append(value)
        return samples

    def _get_experiment(self, experiment_id: str) -> dict[str, Any]:
        try:
            return self._experiments[experiment_id]
        except KeyError as exc:
            raise KeyError(f"Experiment {experiment_id!r} not found.") from exc

    @staticmethod
    def _copy_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            **record,
            "baseline_samples": list(record["baseline_samples"]),
            "candidate_samples": {
                key: list(value) for key, value in record["candidate_samples"].items()
            },
            "candidate_results": {
                key: dict(value) for key, value in record["candidate_results"].items()
            },
        }


AutonomousExperimentEngine = EvolutionExperimentEngine
