"""Deterministic coordinator for one opt-in AutoDev evolution cycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.architecture_evolution import ArchitectureEvolutionEngine
from core.code_quality_engine import CodeQualityEngine
from core.continuous_improvement import ContinuousImprovementEngine
from core.design_pattern_engine import DesignPatternEngine
from core.experiment_engine import EvolutionExperimentEngine
from core.incremental_indexer import IncrementalIndexer
from core.performance_evolution import PerformanceEvolutionEngine
from core.research_engine import ResearchEngine
from core.self_optimizer import SelfOptimizer
from core.software_knowledge_graph import SoftwareKnowledgeGraph
from core.symbol_graph import SymbolGraph


class EvolutionController:
    """Coordinates analysis, evidence gathering, and roadmap publication."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        research_engine: ResearchEngine | None = None,
        experiment_engine: EvolutionExperimentEngine | None = None,
        architecture_engine: ArchitectureEvolutionEngine | None = None,
        self_optimizer: SelfOptimizer | None = None,
        quality_engine: CodeQualityEngine | None = None,
        pattern_engine: DesignPatternEngine | None = None,
        performance_engine: PerformanceEvolutionEngine | None = None,
        improvement_engine: ContinuousImprovementEngine | None = None,
        knowledge_graph: SoftwareKnowledgeGraph | None = None,
        indexer: IncrementalIndexer | None = None,
        learning_engine: Any = None,
        benchmark_engine: Any = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.research_engine = research_engine or ResearchEngine(
            self.project_root / "memory" / "research"
        )
        self.experiment_engine = experiment_engine or EvolutionExperimentEngine(
            self.project_root / "memory" / "experiments"
        )
        self.architecture_engine = architecture_engine or ArchitectureEvolutionEngine()
        self.self_optimizer = self_optimizer or SelfOptimizer()
        self.quality_engine = quality_engine or CodeQualityEngine()
        self.pattern_engine = pattern_engine or DesignPatternEngine()
        self.performance_engine = performance_engine or PerformanceEvolutionEngine()
        self.improvement_engine = improvement_engine or ContinuousImprovementEngine()
        self.knowledge_graph = knowledge_graph or SoftwareKnowledgeGraph()
        self.indexer = indexer or IncrementalIndexer(project_root=self.project_root)
        self.learning_engine = learning_engine
        self.benchmark_engine = benchmark_engine
        self._cycle_number = 0
        self.history: list[dict[str, Any]] = []

    def run_cycle(
        self,
        *,
        symbol_graph: SymbolGraph | None = None,
        observations: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Runs all v4 stages in a fixed order and returns a serializable report."""
        data = dict(observations or {})
        graph = symbol_graph or self.indexer.index_project()
        quality = self.quality_engine.analyze(self.project_root, graph)
        problems = self.research_engine.discover_problems({
            **data,
            "code_quality": quality,
        })
        problem = problems[0] if problems else {
            "problem_id": "system-health-review",
            "title": "Collect evidence for a behavior-preserving improvement",
            "severity": "LOW",
            "evidence": {"issue_count": 0},
            "confidence": 0.5,
        }
        research_plan = self.research_engine.generate_research_plan(problem)
        research_result = self.research_engine.evaluate_results(
            research_plan,
            data.get("research_results", {}),
        )
        published_finding = self.research_engine.publish_findings({
            **research_plan,
            "problem": problem,
            "evaluation": research_result,
            "title": problem["title"],
        })

        experiment_result: dict[str, Any] = {"status": "planned"}
        experiment_inputs = data.get("experiment_candidates", {})
        baseline_runner = data.get("baseline_runner")
        candidate_runners = experiment_inputs if isinstance(experiment_inputs, Mapping) else {}
        if baseline_runner is not None and candidate_runners:
            experiment = self.experiment_engine.create_experiment(
                research_plan["goal"],
                baseline_runner,
                candidate_runners,
            )
            experiment_result = self.experiment_engine.run(experiment["experiment_id"])
        elif baseline_runner is not None or candidate_runners:
            raise ValueError("Experiments require both a baseline runner and at least one candidate runner.")

        architecture = self.architecture_engine.analyze(
            self.project_root,
            graph,
            quality,
        )
        patterns = self.pattern_engine.analyze(self.project_root)
        performance = self.performance_engine.analyze(data.get("performance", {}))
        learning_events = self._learning_events()
        optimizer_metrics = data.get("optimization_metrics", {})
        performance_metrics = data.get("performance", {})
        optimizer_inputs = {
            **(dict(optimizer_metrics) if isinstance(optimizer_metrics, Mapping) else {}),
            **(dict(performance_metrics) if isinstance(performance_metrics, Mapping) else {}),
        }
        optimization = self.self_optimizer.optimize(
            optimizer_inputs,
            recommendations=data.get("optimization_recommendations", {}),
        )
        continuous_inputs = {
            "research": {
                **published_finding,
                "recommendations": [{
                    "title": research_plan["goal"],
                    "priority": problem["severity"].lower(),
                    "evidence": problem.get("evidence", {}),
                }],
            },
            "architecture": architecture,
            "performance": performance,
            "learning": {
                "event_count": len(learning_events),
                "recommendations": data.get("learning_recommendations", []),
            },
            "reflection": data.get("reflection", {}),
            "analytics": data.get("analytics", {}),
            "engineering": {
                "recommendations": quality["recommendations"] + patterns["recommendations"],
            },
        }
        roadmap = self.improvement_engine.generate_roadmap(**continuous_inputs)
        benchmark_data = data.get("benchmarks", {})
        if not isinstance(benchmark_data, Mapping):
            raise TypeError("observations['benchmarks'] must be a mapping.")
        benchmark_data = dict(benchmark_data)
        if self.benchmark_engine is not None:
            scorecard = getattr(self.benchmark_engine, "get_scorecard", None)
            generate_report = getattr(self.benchmark_engine, "generate_report", None)
            if callable(scorecard):
                benchmark_snapshot = scorecard()
            elif callable(generate_report):
                benchmark_snapshot = generate_report()
                to_dict = getattr(benchmark_snapshot, "to_dict", None)
                if callable(to_dict):
                    benchmark_snapshot = to_dict()
            else:
                raise TypeError(
                    "benchmark_engine must provide get_scorecard() or generate_report()."
                )
            if not isinstance(benchmark_snapshot, Mapping):
                raise TypeError("benchmark_engine report must be a mapping.")
            benchmark_data["benchmark_engine"] = dict(benchmark_snapshot)

        self._cycle_number += 1
        cycle_id = f"evolution-{self._cycle_number:04d}"
        self.knowledge_graph.add_repository(
            graph,
            architectures=architecture["architectures"],
            patterns=patterns["patterns"],
        )
        self.knowledge_graph.add_artifact(
            "research", published_finding["finding_id"], problem["title"], published_finding
        )
        if experiment_result.get("experiment_id"):
            self.knowledge_graph.add_artifact(
                "experiment",
                experiment_result["experiment_id"],
                research_plan["goal"],
                experiment_result,
            )
        for event in learning_events:
            event_id = str(event.get("id", event.get("event_id", "")))
            if event_id:
                self.knowledge_graph.add_artifact(
                    "learning", event_id, str(event.get("summary", event_id)), event
                )
        for benchmark_id, benchmark in sorted(benchmark_data.items()):
            self.knowledge_graph.add_artifact(
                "benchmark", str(benchmark_id), str(benchmark_id), benchmark
            )
        cycle_report = {
            "cycle_id": cycle_id,
            "order": [
                "research",
                "experiment",
                "architecture",
                "self_optimization",
                "continuous_improvement",
                "knowledge_graph",
                "evolution_controller",
            ],
            "problem": problem,
            "research_plan": research_plan,
            "research_result": research_result,
            "published_finding": published_finding,
            "experiment": experiment_result,
            "architecture": architecture,
            "code_quality": quality,
            "design_patterns": patterns,
            "performance": performance,
            "optimization": optimization,
            "learning": {"event_count": len(learning_events)},
            "benchmarks": benchmark_data,
            "roadmap": roadmap,
        }
        self.knowledge_graph.add_artifact(
            "evolution", cycle_id, "Autonomous evolution cycle", cycle_report
        )
        cycle_node_id = f"evolution:{cycle_id}"
        self.knowledge_graph.add_edge(
            cycle_node_id,
            f"research:{published_finding['finding_id']}",
            "includes_research",
        )
        for node_type, artifact_id, relation in (
            ("experiment", experiment_result.get("experiment_id"), "includes_experiment"),
        ):
            if artifact_id:
                self.knowledge_graph.add_edge(
                    cycle_node_id,
                    f"{node_type}:{artifact_id}",
                    relation,
                )
        for event in learning_events:
            event_id = str(event.get("id", event.get("event_id", "")))
            if event_id:
                self.knowledge_graph.add_edge(
                    cycle_node_id,
                    f"learning:{event_id}",
                    "includes_learning",
                )
        for benchmark_id in sorted(benchmark_data):
            self.knowledge_graph.add_edge(
                cycle_node_id,
                f"benchmark:{benchmark_id}",
                "includes_benchmark",
            )
        for architecture_record in architecture["architectures"]:
            architecture_name = str(
                architecture_record.get(
                    "pattern_name",
                    architecture_record.get("name", "architecture"),
                )
            )
            self.knowledge_graph.add_edge(
                cycle_node_id,
                f"architecture:{architecture_name}",
                "evaluated_architecture",
            )
        for pattern in patterns["patterns"]:
            self.knowledge_graph.add_edge(
                cycle_node_id,
                f"pattern:{pattern.get('location', pattern.get('kind', 'pattern'))}",
                "detected_pattern",
            )
        cycle_report["knowledge_graph"] = self.knowledge_graph.to_dict()
        self.history.append(cycle_report)
        return cycle_report

    def _learning_events(self) -> list[dict[str, Any]]:
        if self.learning_engine is None or not callable(
            getattr(self.learning_engine, "list_events", None)
        ):
            return []
        events = self.learning_engine.list_events()
        return sorted(
            (event.to_dict() if callable(getattr(event, "to_dict", None)) else dict(event) for event in events),
            key=lambda event: str(event.get("id", event.get("event_id", ""))),
        )
